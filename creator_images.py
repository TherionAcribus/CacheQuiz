import os
import io
from datetime import datetime

from flask import render_template, request, g

from models import db, ImageAsset, AnswerImageLink
from auth import _ensure_creator_page_redirect, _ensure_creator_api

try:
    from PIL import Image
except Exception:
    Image = None


def creator_images_page():
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp
    return render_template('creator_images.html')


def list_creator_images_api():
    denied = _ensure_creator_api()
    if denied:
        return denied

    user = g.current_user
    search = (request.args.get('search') or '').strip()
    selected_id = request.args.get('selected_id', type=int)
    query = ImageAsset.query.filter(ImageAsset.created_by_user_id == user.id)
    if search:
        like = f"%{search}%"
        try:
            from sqlalchemy import or_

            query = query.filter(
                or_(
                    ImageAsset.title.like(like),
                    ImageAsset.filename.like(like),
                    ImageAsset.alt_text.like(like),
                )
            )
        except Exception:
            query = query.filter(ImageAsset.title.like(like))

    images = query.order_by(ImageAsset.created_at.desc()).all()
    if selected_id:
        images.sort(key=lambda img: 0 if img.id == selected_id else 1)
    return render_template('creator_images_list.html', images=images)


def list_creator_images_json():
    """Liste JSON pour les selects (espace créateur)."""
    denied = _ensure_creator_api()
    if denied:
        return denied
    user = g.current_user
    search = (request.args.get('search') or '').strip()
    selected_id = request.args.get('selected_id', type=int)
    query = ImageAsset.query.filter(ImageAsset.created_by_user_id == user.id)
    if search:
        like = f"%{search}%"
        try:
            from sqlalchemy import or_

            query = query.filter(
                or_(
                    ImageAsset.title.like(like),
                    ImageAsset.filename.like(like),
                    ImageAsset.alt_text.like(like),
                )
            )
        except Exception:
            query = query.filter(ImageAsset.title.like(like))

    images = query.order_by(ImageAsset.title).all()
    if selected_id:
        images.sort(key=lambda img: 0 if img.id == selected_id else 1)
    return [
        {
            'id': img.id,
            'title': img.title,
            'filename': img.filename,
            'alt_text': img.alt_text,
        }
        for img in images
    ]


def creator_images_gallery_fragment():
    denied = _ensure_creator_api()
    if denied:
        return denied
    user = g.current_user
    search = (request.args.get('search') or '').strip()
    selected_id = request.args.get('selected_id', type=int)
    select_id = request.args.get('select_id', '')
    partial = (request.args.get('partial') or '0') == '1'

    # Galerie consultable: toutes les images, mais édition/suppression gérées ailleurs et restreintes.
    query = ImageAsset.query
    if search:
        like = f"%{search}%"
        try:
            from sqlalchemy import or_

            query = query.filter(
                or_(
                    ImageAsset.title.like(like),
                    ImageAsset.filename.like(like),
                    ImageAsset.alt_text.like(like),
                )
            )
        except Exception:
            query = query.filter(ImageAsset.title.like(like))

    images = query.order_by(ImageAsset.created_at.desc()).all()
    if selected_id:
        images.sort(key=lambda img: 0 if img.id == selected_id else 1)

    if partial:
        return render_template('images_gallery_grid.html', images=images, selected_id=selected_id or 0, select_id=select_id, creator_mode=True, me=user)
    return render_template('images_gallery.html', images=images, selected_id=selected_id or 0, select_id=select_id, creator_mode=True, me=user)


def creator_new_image():
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp
    embedded = request.args.get('embedded') in ('1', 'true', 'yes')
    select_id = request.args.get('select_id') or ''
    return render_template('image_form.html', image=None, embedded=embedded, select_id=select_id, creator_mode=True, form_action='/api/creator/image')


def creator_edit_image(image_id: int):
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp
    user = g.current_user
    image = ImageAsset.query.get_or_404(image_id)
    if not image.created_by_user_id or image.created_by_user_id != user.id:
        return render_template('creator_access_denied_full.html'), 200
    embedded = request.args.get('embedded') in ('1', 'true', 'yes')
    select_id = request.args.get('select_id') or ''
    return render_template('image_form.html', image=image, embedded=embedded, select_id=select_id, creator_mode=True, form_action=f'/api/creator/image/{image.id}')


def _secure_filename(original_name: str) -> str:
    base = os.path.basename(original_name)
    base = base.replace(' ', '_')
    keep = "-_.()abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    safe = ''.join(ch for ch in base if ch in keep)
    if not safe:
        safe = f'image_{int(datetime.utcnow().timestamp())}.bin'
    return safe


def _optimize_image(file_storage, base_name: str):
    """Optimise l'image (resize + WebP). Retourne (bytes, new_ext, mime) ou (None, None, None)."""
    if Image is None or file_storage is None:
        return None, None, None
    try:
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        if bool(getattr(img, 'is_animated', False)):
            return None, None, None

        has_alpha = (img.mode in ('RGBA', 'LA') or 'transparency' in img.info)
        img = img.convert('RGBA') if has_alpha else img.convert('RGB')

        img.thumbnail((1600, 1600), Image.LANCZOS)
        out = io.BytesIO()
        img.save(out, format='WEBP', quality=80, method=6)
        data = out.getvalue()
        return data, '.webp', 'image/webp'
    except Exception:
        return None, None, None


def create_creator_image(app):
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied
        user = g.current_user

        title = (request.form.get('title') or '').strip()
        alt_text = (request.form.get('alt_text') or '').strip()
        copyright_credits = (request.form.get('copyright_credits') or '').strip()
        copyright_link = (request.form.get('copyright_link') or '').strip()
        file = request.files.get('file')

        if not title:
            return "Titre requis", 400
        if not file:
            return "Fichier requis", 400

        original_secure = _secure_filename(file.filename)
        base_name, _ = os.path.splitext(original_secure)

        optimized_bytes, new_ext, new_mime = _optimize_image(file, base_name)
        if optimized_bytes is not None:
            filename = f"{base_name}{new_ext}"
            counter = 1
            while ImageAsset.query.filter_by(filename=filename).first() is not None:
                filename = f"{base_name}_{counter}{new_ext}"
                counter += 1
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            with open(filepath, 'wb') as f:
                f.write(optimized_bytes)
            size_bytes = len(optimized_bytes)
            mime_type = new_mime
        else:
            filename = original_secure
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            if os.path.exists(filepath):
                name, ext = os.path.splitext(filename)
                filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            base_filename = filename
            counter = 1
            while ImageAsset.query.filter_by(filename=filename).first() is not None:
                name, ext = os.path.splitext(base_filename)
                filename = f"{name}_{counter}{ext}"
                counter += 1
            if filename != base_filename:
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
            file.save(filepath)
            size_bytes = os.path.getsize(filepath)
            mime_type = file.mimetype

        image = ImageAsset(
            title=title,
            filename=filename,
            mime_type=mime_type,
            size_bytes=size_bytes,
            alt_text=alt_text,
            copyright_credits=copyright_credits,
            copyright_link=copyright_link,
            created_by_user_id=user.id,
        )
        db.session.add(image)
        db.session.commit()

        if request.form.get('embedded') in ('1', 'true', 'yes') or request.args.get('embedded') in ('1', 'true', 'yes'):
            return {
                'created_image': {
                    'id': image.id,
                    'title': image.title,
                    'filename': image.filename,
                    'alt_text': image.alt_text,
                    'copyright_credits': image.copyright_credits,
                    'copyright_link': image.copyright_link,
                },
                'select_id': request.form.get('select_id') or request.args.get('select_id') or '',
            }

        images = ImageAsset.query.filter(ImageAsset.created_by_user_id == user.id).order_by(ImageAsset.created_at.desc()).all()
        return render_template('creator_images_list.html', images=images)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def update_creator_image(image_id: int, app):
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied
        user = g.current_user

        image = ImageAsset.query.get_or_404(image_id)
        if not image.created_by_user_id or image.created_by_user_id != user.id:
            return "Accès refusé", 403
        title = (request.form.get('title') or '').strip()
        alt_text = (request.form.get('alt_text') or '').strip()
        copyright_credits = (request.form.get('copyright_credits') or '').strip()
        copyright_link = (request.form.get('copyright_link') or '').strip()
        file = request.files.get('file')

        if not title:
            return "Titre requis", 400

        image.title = title
        image.alt_text = alt_text
        image.copyright_credits = copyright_credits
        image.copyright_link = copyright_link

        if file:
            original_secure = _secure_filename(file.filename)
            base_name, _ = os.path.splitext(original_secure)
            optimized_bytes, new_ext, new_mime = _optimize_image(file, base_name)
            if optimized_bytes is not None:
                filename = f"{base_name}{new_ext}"
                counter = 1
                while ImageAsset.query.filter(ImageAsset.filename == filename, ImageAsset.id != image.id).first() is not None:
                    filename = f"{base_name}_{counter}{new_ext}"
                    counter += 1
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(filepath, 'wb') as f:
                    f.write(optimized_bytes)
                image.filename = filename
                image.size_bytes = len(optimized_bytes)
                image.mime_type = new_mime
            else:
                filename = original_secure
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(filepath):
                    name, ext = os.path.splitext(filename)
                    filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                base_filename = filename
                counter = 1
                while ImageAsset.query.filter(ImageAsset.filename == filename, ImageAsset.id != image.id).first() is not None:
                    name, ext = os.path.splitext(base_filename)
                    filename = f"{name}_{counter}{ext}"
                    counter += 1
                if filename != base_filename:
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image.filename = filename
                image.size_bytes = os.path.getsize(filepath)
                image.mime_type = file.mimetype

        image.updated_at = datetime.utcnow()
        db.session.commit()

        images = ImageAsset.query.filter(ImageAsset.created_by_user_id == user.id).order_by(ImageAsset.created_at.desc()).all()
        return render_template('creator_images_list.html', images=images)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def delete_creator_image(image_id: int, app):
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied
        user = g.current_user

        image = ImageAsset.query.get_or_404(image_id)
        if not image.created_by_user_id or image.created_by_user_id != user.id:
            return "Accès refusé", 403

        # Détacher les liens AnswerImageLink
        AnswerImageLink.query.filter_by(image_id=image.id).delete()

        # Supprimer le fichier si présent
        try:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

        db.session.delete(image)
        db.session.commit()

        images = ImageAsset.query.filter(ImageAsset.created_by_user_id == user.id).order_by(ImageAsset.created_at.desc()).all()
        return render_template('creator_images_list.html', images=images)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def confirm_delete_creator_image(image_id: int):
    """Retourne une modale de confirmation (cohérente) pour supprimer une image."""
    denied = _ensure_creator_api()
    if denied:
        return denied

    user = g.current_user
    image = ImageAsset.query.get_or_404(image_id)
    if not image.created_by_user_id or image.created_by_user_id != user.id:
        return "Accès refusé", 403

    inner = render_template(
        'creator_confirm_modal.html',
        title="Supprimer l’image",
        message=f"Confirmez la suppression de l’image « {image.title} ». Cette action est irréversible.",
        action_url=f"/api/creator/image/{image.id}",
        action_method="delete",
        target_selector="#images-list",
        confirm_label="🗑️ Supprimer",
        confirm_button_class="btn-danger",
    )
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"

