from flask import render_template, request, redirect
from models import db, BroadTheme, SpecificTheme, Question, User, Keyword
from auth import _ensure_admin_page_redirect, _ensure_perm_api
from datetime import datetime


def list_themes():
    """Retourner la liste hiérarchique des thèmes et sous-thèmes en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('themes_unified_list.html', themes=themes)


def list_themes_json():
    """Retourner la liste des thèmes en JSON (pour les selects)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return [{'id': t.id, 'name': t.name} for t in themes]


def list_subthemes_json():
    """Retourner la liste des sous-thèmes en JSON"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    broad_theme_id = request.args.get('broad_theme_id', type=int)
    query = SpecificTheme.query
    if broad_theme_id:
        query = query.filter_by(broad_theme_id=broad_theme_id)

    subthemes = query.order_by(SpecificTheme.name).all()
    return [{'id': t.id, 'name': t.name, 'broad_theme_id': t.broad_theme_id} for t in subthemes]


def list_authors_json():
    """Retourner la liste des auteurs en JSON"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    # On ne liste que les utilisateurs qui ont créé au moins une question
    authors = db.session.query(User).join(Question).distinct().order_by(User.username).all()
    return [{'id': u.id, 'username': u.username} for u in authors]


def list_difficulties_json():
    """Retourner la liste des difficultés en JSON"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    # On récupère les difficultés existantes ou une liste par défaut
    diffs = db.session.query(Question.difficulty_level).distinct().filter(Question.difficulty_level.isnot(None)).order_by(Question.difficulty_level).all()
    existing = [d[0] for d in diffs]
    if not existing:
        existing = [1, 2, 3, 4, 5]
    return [{'id': d, 'name': f"Niveau {d}"} for d in existing]


def new_theme():
    """Formulaire pour créer un nouveau thème"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    embedded = request.args.get('embedded') in ('1', 'true', 'yes')
    select_id = request.args.get('select_id') or ''
    return render_template('theme_form.html', theme=None, embedded=embedded, select_id=select_id)


def edit_theme(theme_id):
    """Formulaire pour éditer un thème"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    theme = BroadTheme.query.get_or_404(theme_id)
    return render_template('theme_form.html', theme=theme)


def create_theme():
    """Créer un nouveau thème"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        data = request.form

        theme = BroadTheme(
            name=data.get('name'),
            description=data.get('description'),
            language=data.get('language', 'fr'),
            icon=data.get('icon'),
            color=data.get('color'),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None
        )

        db.session.add(theme)
        db.session.commit()

        # Si formulaire embarqué (modale au-dessus d'une autre modale): renvoyer JSON
        if request.form.get('embedded') in ('1', 'true', 'yes'):
            return {
                'created_theme': {
                    'id': theme.id,
                    'name': theme.name,
                    'language': theme.language,
                    'icon': theme.icon
                },
                'select_id': request.form.get('select_id')
            }

        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_unified_list.html', themes=themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def update_theme(theme_id):
    """Mettre à jour un thème existant"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        theme = BroadTheme.query.get_or_404(theme_id)
        data = request.form

        # Mettre à jour les champs
        theme.name = data.get('name')
        theme.description = data.get('description')
        theme.language = data.get('language', 'fr')
        theme.icon = data.get('icon')
        theme.color = data.get('color')
        theme.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        theme.updated_at = datetime.utcnow()

        db.session.commit()

        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_unified_list.html', themes=themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def delete_theme(theme_id):
    """Supprimer un thème"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        theme = BroadTheme.query.get_or_404(theme_id)

        # Vérifier si des questions utilisent ce thème
        question_count = theme.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer ce thème : {question_count} question(s) l'utilisent encore.", 400

        db.session.delete(theme)
        db.session.commit()

        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_unified_list.html', themes=themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def specific_themes_page():
    """Page de gestion des sous-thèmes"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('specific_themes.html')


def list_specific_themes():
    """Retourner la liste des sous-thèmes en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('themes_unified_list.html', themes=themes)


def new_specific_theme():
    """Formulaire pour créer un nouveau sous-thème"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    embedded = request.args.get('embedded') in ('1', 'true', 'yes')
    select_id = request.args.get('select_id') or ''
    broad_theme_id = request.args.get('broad_theme_id')
    broad_themes = BroadTheme.query.order_by(BroadTheme.name).all()

    # Récupérer le thème pré-sélectionné pour afficher sa couleur
    preselected_theme = None
    if broad_theme_id:
        preselected_theme = BroadTheme.query.get(int(broad_theme_id))

    return render_template('specific_theme_form.html', specific_theme=None, broad_themes=broad_themes, embedded=embedded, select_id=select_id, preselected_broad_theme_id=broad_theme_id, preselected_theme=preselected_theme)


def edit_specific_theme(specific_theme_id):
    """Formulaire pour éditer un sous-thème"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    specific_theme = SpecificTheme.query.get_or_404(specific_theme_id)
    broad_themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('specific_theme_form.html', specific_theme=specific_theme, broad_themes=broad_themes)


def create_specific_theme():
    """Créer un nouveau sous-thème"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        data = request.form

        specific_theme = SpecificTheme(
            name=data.get('name'),
            description=data.get('description'),
            language=data.get('language', 'fr'),
            icon=data.get('icon'),
            color=data.get('color'),
            broad_theme_id=int(data.get('broad_theme_id')),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None
        )

        db.session.add(specific_theme)
        db.session.commit()

        # Si formulaire embarqué (modale au-dessus d'une autre modale): renvoyer JSON
        if request.form.get('embedded') in ('1', 'true', 'yes'):
            return {
                'created_specific_theme': {
                    'id': specific_theme.id,
                    'name': specific_theme.name,
                    'broad_theme_id': specific_theme.broad_theme_id,
                    'language': specific_theme.language,
                    'icon': specific_theme.icon
                },
                'select_id': request.form.get('select_id')
            }

        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_unified_list.html', themes=themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def update_specific_theme(specific_theme_id):
    """Mettre à jour un sous-thème existant"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        specific_theme = SpecificTheme.query.get_or_404(specific_theme_id)
        data = request.form

        # Mettre à jour les champs
        specific_theme.name = data.get('name')
        specific_theme.description = data.get('description')
        specific_theme.language = data.get('language', 'fr')
        specific_theme.icon = data.get('icon')
        specific_theme.color = data.get('color')
        specific_theme.broad_theme_id = int(data.get('broad_theme_id'))
        specific_theme.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        specific_theme.updated_at = datetime.utcnow()

        db.session.commit()

        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_unified_list.html', themes=themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def delete_specific_theme(specific_theme_id):
    """Supprimer un sous-thème"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        specific_theme = SpecificTheme.query.get_or_404(specific_theme_id)

        # Vérifier si des questions utilisent ce sous-thème
        question_count = specific_theme.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer ce sous-thème : {question_count} question(s) l'utilisent encore.", 400

        db.session.delete(specific_theme)
        db.session.commit()

        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_unified_list.html', themes=themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def get_specific_themes_for_broad_theme():
    """Obtenir les sous-thèmes pour un thème large (retourne HTML pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    broad_theme_id = request.args.get('broad_theme_id')
    if broad_theme_id and broad_theme_id.isdigit():
        specific_themes = SpecificTheme.query.filter_by(broad_theme_id=int(broad_theme_id)).order_by(SpecificTheme.name).all()
    else:
        specific_themes = []
    return render_template('specific_theme_options.html', specific_themes=specific_themes)


def themes_unified_page():
    """Page de gestion unifiée des thèmes et sous-thèmes"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('themes_unified.html')
