from flask import render_template, request, redirect, url_for
from models import db, ImageAsset, AnswerImageLink
from auth import _has_perm, _ensure_admin_page_redirect, _ensure_perm_api
from datetime import datetime
import os
import io
try:
    from PIL import Image
except Exception:
    Image = None


def images_page():
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('images.html')


def list_images_api():
    denied = _ensure_perm_api()
    if denied:
        return denied
    search = request.args.get('search', '').strip()
    selected_id = request.args.get('selected_id', type=int)
    query = ImageAsset.query
    if search:
        like = f"%{search}%"
        try:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    ImageAsset.title.like(like),
                    ImageAsset.filename.like(like),
                    ImageAsset.alt_text.like(like)
                )
            )
        except Exception:
            # Fallback: filtre sur le titre uniquement
            query = query.filter(ImageAsset.title.like(like))
    images = query.order_by(ImageAsset.created_at.desc()).all()
    if selected_id:
        images.sort(key=lambda img: 0 if img.id == selected_id else 1)
    return render_template('images_list.html', images=images)


def list_images_json():
    """Retourne la liste des images au format JSON pour les selects"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    search = request.args.get('search', '').strip()
    selected_id = request.args.get('selected_id', type=int)
    query = ImageAsset.query
    if search:
        like = f"%{search}%"
        try:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    ImageAsset.title.like(like),
                    ImageAsset.filename.like(like),
                    ImageAsset.alt_text.like(like)
                )
            )
        except Exception:
            query = query.filter(ImageAsset.title.like(like))
    images = query.order_by(ImageAsset.title).all()
    if selected_id:
        images.sort(key=lambda img: 0 if img.id == selected_id else 1)
    return [{
        'id': img.id,
        'title': img.title,
        'filename': img.filename,
        'alt_text': img.alt_text
    } for img in images]


def images_gallery_fragment():
    denied = _ensure_perm_api()
    if denied:
        return denied
    search = request.args.get('search', '').strip()
    selected_id = request.args.get('selected_id', type=int)
    select_id = request.args.get('select_id', '')
    partial = request.args.get('partial', '0') == '1'
    print(f"[DEBUG] /api/images/gallery called with search='{search}', selected_id={selected_id}, select_id='{select_id}', partial={partial}")
    query = ImageAsset.query
    if search:
        like = f"%{search}%"
        print(f"[DEBUG] Filtering with search pattern: {like}")
        try:
            from sqlalchemy import or_
            query = query.filter(
                or_(
                    ImageAsset.title.like(like),
                    ImageAsset.filename.like(like),
                    ImageAsset.alt_text.like(like)
                )
            )
        except Exception:
            query = query.filter(ImageAsset.title.like(like))
    images = query.order_by(ImageAsset.created_at.desc()).all()
    print(f"[DEBUG] Found {len(images)} images after filtering")
    if selected_id:
        images.sort(key=lambda img: 0 if img.id == selected_id else 1)

    if partial:
        # Retourner seulement la grille d'images pour les mises à jour partielles
        return render_template('images_gallery_grid.html', images=images, selected_id=selected_id or 0, select_id=select_id)
    else:
        # Retourner le HTML complet pour l'ouverture initiale
        return render_template('images_gallery.html', images=images, selected_id=selected_id or 0, select_id=select_id)


def new_image():
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    embedded = request.args.get('embedded') in ('1', 'true', 'yes')
    select_id = request.args.get('select_id') or ''
    return render_template('image_form.html', image=None, embedded=embedded, select_id=select_id)


def edit_image(image_id: int):
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    image = ImageAsset.query.get_or_404(image_id)
    embedded = request.args.get('embedded') in ('1', 'true', 'yes')
    select_id = request.args.get('select_id') or ''
    return render_template('image_form.html', image=image, embedded=embedded, select_id=select_id)


def _secure_filename(original_name: str) -> str:
    # Sécuriser le nom de fichier simplement (remplacer espaces, enlever caractères spéciaux)
    base = os.path.basename(original_name)
    base = base.replace(' ', '_')
    keep = "-_.()abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    safe = ''.join(ch for ch in base if ch in keep)
    if not safe:
        safe = f'image_{int(datetime.utcnow().timestamp())}.bin'
    return safe


def _optimize_image(file_storage, base_name: str):
    """Optimise l'image pour le web (resize + WebP). Retourne (bytes, new_ext, mime) ou (None, None, None)."""
    if Image is None or file_storage is None:
        return None, None, None
    try:
        file_storage.stream.seek(0)
        img = Image.open(file_storage.stream)
        # GIF animé: on ne touche pas
        if bool(getattr(img, 'is_animated', False)):
            return None, None, None

        has_alpha = (img.mode in ('RGBA', 'LA') or 'transparency' in img.info)
        img = img.convert('RGBA') if has_alpha else img.convert('RGB')

        # Redimension max 1600px
        max_size = (1600, 1600)
        img.thumbnail(max_size, Image.LANCZOS)

        out = io.BytesIO()
        img.save(out, format='WEBP', quality=80, method=6)
        data = out.getvalue()
        return data, '.webp', 'image/webp'
    except Exception:
        return None, None, None


def create_image(app):
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        title = request.form.get('title', '').strip()
        alt_text = request.form.get('alt_text', '').strip()
        copyright_credits = request.form.get('copyright_credits', '').strip()
        copyright_link = request.form.get('copyright_link', '').strip()
        file = request.files.get('file')
        if not title:
            return "Titre requis", 400
        if not file:
            return "Fichier requis", 400

        # Nom de base et optimisation
        original_secure = _secure_filename(file.filename)
        base_name, orig_ext = os.path.splitext(original_secure)

        optimized_bytes, new_ext, new_mime = _optimize_image(file, base_name)
        if optimized_bytes is not None:
            filename = f"{base_name}{new_ext}"
            # Unicité DB uniquement
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
            # Fallback: sauvegarde brute
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

        image = ImageAsset(title=title, filename=filename, mime_type=mime_type, size_bytes=size_bytes, alt_text=alt_text, copyright_credits=copyright_credits, copyright_link=copyright_link)
        db.session.add(image)
        db.session.commit()

        # Si formulaire embarqué (modale au-dessus d'une autre modale): renvoyer JSON
        if request.form.get('embedded') in ('1', 'true', 'yes') or request.args.get('embedded') in ('1', 'true', 'yes'):
            return {
                'created_image': {
                    'id': image.id,
                    'title': image.title,
                    'filename': image.filename,
                    'alt_text': image.alt_text,
                    'copyright_credits': image.copyright_credits,
                    'copyright_link': image.copyright_link
                },
                'select_id': request.form.get('select_id') or request.args.get('select_id') or ''
            }

        images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
        return render_template('images_list.html', images=images)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


def update_image(image_id: int, app):
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        image = ImageAsset.query.get_or_404(image_id)
        title = request.form.get('title', '').strip()
        alt_text = request.form.get('alt_text', '').strip()
        copyright_credits = request.form.get('copyright_credits', '').strip()
        copyright_link = request.form.get('copyright_link', '').strip()
        file = request.files.get('file')

        if title:
            image.title = title
        image.alt_text = alt_text
        image.copyright_credits = copyright_credits
        image.copyright_link = copyright_link

        if file:
            original_secure = _secure_filename(file.filename)
            base_name, orig_ext = os.path.splitext(original_secure)

            optimized_bytes, new_ext, new_mime = _optimize_image(file, base_name)
            if optimized_bytes is not None:
                filename = f"{base_name}{new_ext}"
                counter = 1
                while ImageAsset.query.filter_by(filename=filename).first() is not None and filename != image.filename:
                    filename = f"{base_name}_{counter}{new_ext}"
                    counter += 1
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                with open(filepath, 'wb') as f:
                    f.write(optimized_bytes)
                image.filename = filename
                image.mime_type = new_mime
                image.size_bytes = len(optimized_bytes)
                image.updated_at = datetime.utcnow()
            else:
                filename = original_secure
                filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                if os.path.exists(filepath):
                    name, ext = os.path.splitext(filename)
                    filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"
                    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(filepath)
                image.filename = filename
                image.mime_type = file.mimetype
                image.size_bytes = os.path.getsize(filepath)
                image.updated_at = datetime.utcnow()

        db.session.commit()
        images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
        return render_template('images_list.html', images=images)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


def delete_image(image_id: int, app):
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        image = ImageAsset.query.get_or_404(image_id)
        # Empêcher la suppression si utilisée par des réponses ou questions
        if image.questions.count() > 0 or AnswerImageLink.query.filter_by(image_id=image.id).count() > 0:
            return "Impossible de supprimer: image utilisée.", 400

        # Supprimer le fichier physique si présent
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], image.filename)
        try:
            if os.path.exists(filepath):
                os.remove(filepath)
        except Exception:
            pass

        db.session.delete(image)
        db.session.commit()

        images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
        return render_template('images_list.html', images=images)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


