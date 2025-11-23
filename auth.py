from flask import Flask, render_template, request, redirect, session, g, url_for, make_response, flash
from models import db, User
from werkzeug.security import check_password_hash, generate_password_hash
import json
import re


def quick_login():
    """Connexion rapide sans mot de passe pour les utilisateurs existants ou création d'un nouveau compte."""
    pseudo = (request.form.get('pseudo') or '').strip()
    if not pseudo:
        return "Pseudo requis", 400

    next_url = (request.form.get('next') or request.headers.get('HX-Redirect') or url_for('play_quiz'))
    source = (request.form.get('source') or 'widget')

    # Chercher utilisateur par username exact
    user = User.query.filter_by(username=pseudo).first()

    if not user:
        # Créer un user sans mot de passe (joueur standard)
        user = User(username=pseudo, email=None, is_active=True)
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        # Assurer que le widget reflète l'état connecté dans cette même réponse
        g.current_user = user
        resp = make_response('')
        resp.headers['HX-Redirect'] = next_url
        resp.headers['HX-Trigger'] = json.dumps({'quiz-login-success': {'source': source, 'username': user.username}})
        return resp
    elif user.password_hash:
        # Si l'utilisateur a un mot de passe, afficher le formulaire de connexion avec pseudo pré-rempli
        if source == 'play-start':
            resp = make_response('')
            resp.headers['HX-Trigger'] = json.dumps({'quiz-login-password-required': {'username': pseudo, 'next': next_url}})
            return resp
        return render_template(
            'auth_widget.html',
            login_username=pseudo,
            show_password_form=True,
            next_url=next_url,
            source=source,
        )
    else:
        # Utilisateur existant sans mot de passe, connexion directe
        session['user_id'] = user.id
        # Assurer que le widget reflète l'état connecté dans cette même réponse
        g.current_user = user
        resp = make_response('')
        resp.headers['HX-Redirect'] = next_url
        resp.headers['HX-Trigger'] = json.dumps({'quiz-login-success': {'source': source, 'username': user.username}})
        return resp


def logout():
    """Déconnexion de l'utilisateur."""
    session.pop('user_id', None)
    # Assurer que le widget reflète l'état déconnecté dans cette même réponse
    g.current_user = None
    resp = make_response('')
    resp.headers['HX-Redirect'] = url_for('index')
    return resp


def widget_login():
    """Connexion depuis le widget avec pseudo + mot de passe."""
    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()
    next_url = (request.form.get('next') or request.headers.get('HX-Redirect') or url_for('play_quiz'))
    source = (request.form.get('source') or 'widget')

    if not username or not password:
        if source == 'play-start':
            resp = make_response('')
            resp.headers['HX-Trigger'] = json.dumps({'quiz-login-password-error': {'message': "Pseudo et mot de passe requis"}})
            return resp
        return render_template(
            'auth_widget.html',
            login_username=username,
            show_password_form=True,
            error_message="Pseudo et mot de passe requis",
            next_url=next_url,
            source=source,
        )

    user = User.query.filter_by(username=username).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        if source == 'play-start':
            resp = make_response('')
            resp.headers['HX-Trigger'] = json.dumps({'quiz-login-password-error': {'message': "Identifiants invalides"}})
            return resp
        return render_template(
            'auth_widget.html',
            login_username=username,
            show_password_form=True,
            error_message="Identifiants invalides",
            next_url=next_url,
            source=source,
        )

    session['user_id'] = user.id
    # Assurer que le widget reflète l'état connecté dans cette même réponse
    g.current_user = user
    resp = make_response('')
    resp.headers['HX-Redirect'] = next_url
    resp.headers['HX-Trigger'] = json.dumps({'quiz-login-success': {'source': source, 'username': user.username}})
    return resp


def upgrade_account():
    """Permet à un utilisateur connecté sans mot de passe d'ajouter email/mot de passe."""
    if not getattr(g, 'current_user', None):
        return "<div class='alert alert-danger'>Vous devez être connecté pour effectuer cette action.</div>", 403

    user = g.current_user
    if user.password_hash:
        return "<div class='alert alert-warning'>Votre compte est déjà sécurisé avec un mot de passe.</div>"

    email = (request.form.get('email') or '').strip()
    password = request.form.get('password', '').strip()
    password_confirm = request.form.get('password_confirm', '').strip()

    errors = []

    # Validation email (optionnel)
    if email and not re.match(r'^[^\s@]+@[^\s@]+\.[^\s@]+$', email):
        errors.append("Format d'email invalide")

    # Validation mot de passe
    if not password:
        errors.append("Le mot de passe est requis")
    elif len(password) < 6:
        errors.append("Le mot de passe doit contenir au moins 6 caractères")
    elif password != password_confirm:
        errors.append("Les mots de passe ne correspondent pas")

    if errors:
        error_html = "<div class='alert alert-danger'><ul>"
        for error in errors:
            error_html += f"<li>{error}</li>"
        error_html += "</ul></div>"
        return error_html

    # Mettre à jour l'utilisateur
    user.email = email if email else None
    user.password_hash = generate_password_hash(password)
    db.session.commit()

    # Fermer la modal et afficher un message de succès
    return """
    <div class='success-message'>
        <div style='text-align: center; padding: 2rem;'>
            <h3 style='color: var(--success-color); margin-bottom: 1rem;'>✅ Compte sécurisé !</h3>
            <p>Votre compte est maintenant protégé par un mot de passe.</p>
            <p>Vous pouvez accéder à vos statistiques détaillées et votre progression est sauvegardée.</p>
            <button type='button' class='btn btn-primary' onclick='hideUpgradeModal(); location.reload();' style='margin-top: 1rem;'>
                Continuer à jouer
            </button>
        </div>
    </div>
    """


def login_page():
    """Page de connexion traditionnelle."""
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        password = (request.form.get('password') or '').strip()
        if not username or not password:
            return render_template('login.html', error="Identifiants requis")
        user = User.query.filter_by(username=username).first()
        if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
            return render_template('login.html', error="Identifiants invalides")
        session['user_id'] = user.id
        next_url = request.args.get('next') or url_for('play_quiz')
        return redirect(next_url)
    return render_template('login.html')


def register_page():
    """Page d'inscription d'un nouvel utilisateur."""
    if request.method == 'POST':
        username = (request.form.get('username') or '').strip()
        email = (request.form.get('email') or '').strip() or None
        # display_name supprimé, on utilise directement le username
        password = (request.form.get('password') or '').strip()
        password2 = (request.form.get('password2') or '').strip()
        if not username or not password:
            return render_template('register.html', error="Nom d'utilisateur et mot de passe requis")
        if password != password2:
            return render_template('register.html', error="Les mots de passe ne correspondent pas")
        if User.query.filter_by(username=username).first():
            return render_template('register.html', error="Ce nom d'utilisateur est déjà pris")
        # Créer l'utilisateur avec mot de passe hashé
        user = User(
            username=username,
            email=email,
            is_active=True,
            password_hash=generate_password_hash(password)
        )
        db.session.add(user)
        db.session.commit()
        session['user_id'] = user.id
        return redirect(url_for('play_quiz'))
    return render_template('register.html')
