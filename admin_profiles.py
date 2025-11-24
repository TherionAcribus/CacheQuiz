from flask import render_template, request, redirect, url_for
from models import db, Profile
from auth import _ensure_admin_page_redirect, _ensure_perm_api, _deny_access, _has_perm
from datetime import datetime


def profiles_page():
    """Page de gestion des profils"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_profiles'):
        return redirect(url_for('play_quiz'))
    return render_template('profiles.html')


def list_profiles():
    """Retourner la liste des profils en HTML (pour HTMX)"""
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied
    profiles = Profile.query.order_by(Profile.name).all()
    return render_template('profiles_list.html', profiles=profiles)


def new_profile():
    """Formulaire pour créer un nouveau profil"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_profiles'):
        return _deny_access("Permission 'can_manage_profiles' requise")
    return render_template('profile_form.html', profile=None)


def edit_profile(profile_id: int):
    """Formulaire pour éditer un profil"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_profiles'):
        return _deny_access("Permission 'can_manage_profiles' requise")
    profile = Profile.query.get_or_404(profile_id)
    return render_template('profile_form.html', profile=profile)


def _bool_from_form(key: str) -> bool:
    return request.form.get(key) == 'on'


def create_profile():
    """Créer un nouveau profil"""
    try:
        denied = _ensure_perm_api('can_manage_profiles')
        if denied:
            return denied
        data = request.form
        name = (data.get('name') or '').strip()
        if not name:
            return "Nom requis", 400

        profile = Profile(
            name=name,
            description=(data.get('description') or '').strip() or None,
            can_access_admin=_bool_from_form('can_access_admin'),
            can_create_question=_bool_from_form('can_create_question'),
            can_update_delete_own_question=_bool_from_form('can_update_delete_own_question'),
            can_update_delete_any_question=_bool_from_form('can_update_delete_any_question'),
            can_create_rule=_bool_from_form('can_create_rule'),
            can_update_delete_own_rule=_bool_from_form('can_update_delete_own_rule'),
            can_update_delete_any_rule=_bool_from_form('can_update_delete_any_rule'),
            can_manage_users=_bool_from_form('can_manage_users'),
            can_manage_profiles=_bool_from_form('can_manage_profiles'),
        )

        db.session.add(profile)
        db.session.commit()

        profiles = Profile.query.order_by(Profile.name).all()
        return render_template('profiles_list.html', profiles=profiles)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


def update_profile(profile_id: int):
    """Mettre à jour un profil existant"""
    try:
        denied = _ensure_perm_api('can_manage_profiles')
        if denied:
            return denied
        profile = Profile.query.get_or_404(profile_id)
        data = request.form

        name = (data.get('name') or '').strip()
        if name:
            profile.name = name
        profile.description = (data.get('description') or '').strip() or None
        profile.can_access_admin = _bool_from_form('can_access_admin')
        profile.can_create_question = _bool_from_form('can_create_question')
        profile.can_update_delete_own_question = _bool_from_form('can_update_delete_own_question')
        profile.can_update_delete_any_question = _bool_from_form('can_update_delete_any_question')
        profile.can_create_rule = _bool_from_form('can_create_rule')
        profile.can_update_delete_own_rule = _bool_from_form('can_update_delete_own_rule')
        profile.can_update_delete_any_rule = _bool_from_form('can_update_delete_any_rule')
        profile.can_manage_users = _bool_from_form('can_manage_users')
        profile.can_manage_profiles = _bool_from_form('can_manage_profiles')
        profile.updated_at = datetime.utcnow()

        db.session.commit()

        profiles = Profile.query.order_by(Profile.name).all()
        return render_template('profiles_list.html', profiles=profiles)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


def delete_profile(profile_id: int):
    """Supprimer un profil"""
    try:
        denied = _ensure_perm_api('can_manage_profiles')
        if denied:
            return denied
        profile = Profile.query.get_or_404(profile_id)
        # Empêcher la suppression si des utilisateurs utilisent ce profil
        if profile.users.count() > 0:
            return "Impossible de supprimer: des utilisateurs utilisent ce profil.", 400

        db.session.delete(profile)
        db.session.commit()

        profiles = Profile.query.order_by(Profile.name).all()
        return render_template('profiles_list.html', profiles=profiles)
    except Exception as e:
        return f"Erreur: {str(e)}", 400
