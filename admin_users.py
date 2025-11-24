from flask import render_template, request, redirect, url_for
from models import db, User, Profile
from auth import _ensure_admin_page_redirect, _ensure_perm_api, _deny_access, _has_perm
from werkzeug.security import generate_password_hash
from datetime import datetime


def users_page():
    """Page de gestion des utilisateurs"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_users'):
        return redirect(url_for('play_quiz'))
    return render_template('users.html')


def list_users():
    """Retourner la liste des utilisateurs en HTML (pour HTMX)"""
    denied = _ensure_perm_api('can_manage_users')
    if denied:
        return denied
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('users_list.html', users=users)


def new_user():
    """Formulaire pour créer un nouvel utilisateur"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_users'):
        return _deny_access("Permission 'can_manage_users' requise")
    profiles = Profile.query.order_by(Profile.name).all()
    return render_template('user_form.html', user=None, profiles=profiles)


def edit_user(user_id):
    """Formulaire pour éditer un utilisateur"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_users'):
        return _deny_access("Permission 'can_manage_users' requise")
    user = User.query.get_or_404(user_id)
    profiles = Profile.query.order_by(Profile.name).all()
    return render_template('user_form.html', user=user, profiles=profiles)


def create_user():
    """Créer un nouvel utilisateur"""
    try:
        denied = _ensure_perm_api('can_manage_users')
        if denied:
            return denied
        data = request.form

        # Validation du mot de passe pour les profils admin
        profile_id = data.get('profile_id')
        password = (data.get('password') or '').strip()

        if profile_id and profile_id.isdigit():
            profile = Profile.query.get(int(profile_id))
            if profile and profile.can_access_admin and not password:
                return "Mot de passe requis pour les utilisateurs avec accès administration", 400

        user = User(
            username=data.get('username'),
            email=data.get('email') or None,
            is_active=data.get('is_active') == 'on',
            profile_id=(int(profile_id) if profile_id and profile_id.isdigit() else None)
        )

        # Définir le mot de passe si fourni
        if password:
            user.password_hash = generate_password_hash(password)

        db.session.add(user)
        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.username).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def update_user(user_id):
    """Mettre à jour un utilisateur existant"""
    try:
        denied = _ensure_perm_api('can_manage_users')
        if denied:
            return denied
        user = User.query.get_or_404(user_id)
        data = request.form

        # Validation du mot de passe pour les profils admin
        profile_id = data.get('profile_id')
        password = (data.get('password') or '').strip()

        if profile_id and profile_id.isdigit():
            profile = Profile.query.get(int(profile_id))
            if profile and profile.can_access_admin and not password and not user.password_hash:
                return "Mot de passe requis pour les utilisateurs avec accès administration", 400

        # Validation supplémentaire : si on attribue un profil admin à un utilisateur sans mot de passe
        new_profile_id = int(profile_id) if profile_id and profile_id.isdigit() else None
        if new_profile_id and new_profile_id != user.profile_id:
            new_profile = Profile.query.get(new_profile_id)
            if new_profile and new_profile.can_access_admin and not user.password_hash and not password:
                return "Impossible d'attribuer un profil admin sans mot de passe. Définissez d'abord un mot de passe.", 400

        # Mettre à jour les champs
        user.username = data.get('username')
        user.email = data.get('email') or None
        user.is_active = data.get('is_active') == 'on'
        user.profile_id = new_profile_id

        # Mettre à jour le mot de passe si fourni
        if password:
            user.password_hash = generate_password_hash(password)

        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.username).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def delete_user(user_id):
    """Désactiver un utilisateur (soft delete)"""
    try:
        denied = _ensure_perm_api('can_manage_users')
        if denied:
            return denied
        user = User.query.get_or_404(user_id)

        # Vérifier si l'utilisateur a des questions
        question_count = user.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer cet utilisateur : {question_count} question(s) lui appartiennent encore.", 400

        # Soft delete : désactiver au lieu de supprimer
        user.is_active = False
        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.username).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400
