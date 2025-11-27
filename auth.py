from flask import render_template, request, redirect, session, g, url_for, make_response
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
        # Retourner le formulaire complet avec les erreurs
        return f"""
        <form id="upgrade-form" hx-post="/auth/upgrade-account" hx-target="#upgrade-form" hx-swap="outerHTML">
            {error_html}
            <div class="form-group">
                <label for="email">Email (optionnel)</label>
                <input type="email" id="email" name="email" value="{email or ''}" placeholder="votre.email@exemple.com">
                <small>Pour récupérer votre compte si nécessaire</small>
            </div>
            <div class="form-group">
                <label for="password">Mot de passe *</label>
                <input type="password" id="password" name="password" value="{password}" required placeholder="Choisissez un mot de passe">
                <small>Minimum 6 caractères</small>
            </div>
            <div class="form-group">
                <label for="password_confirm">Confirmer le mot de passe *</label>
                <input type="password" id="password_confirm" name="password_confirm" value="{password_confirm}" required
                    placeholder="Retapez le mot de passe">
            </div>
            <div class="form-actions">
                <button type="submit" class="btn btn-primary">Créer mon compte</button>
                <button type="button" class="btn btn-secondary" onclick="hideUpgradeModal()">Annuler</button>
            </div>
        </form>
        """

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


# Helper functions for permissions
def _has_perm(perm_attr: str) -> bool:
    """Check if current user has a specific permission."""
    user = getattr(g, 'current_user', None)
    return bool(user and user.has_perm(perm_attr))


def _ensure_admin_page_redirect():
    """Pour les pages complètes: redirige si pas d'accès admin."""
    if not _has_perm('can_access_admin'):
        return redirect(url_for('access_denied_page'))
    return None


def _ensure_perm_api(*perm_attrs: str):
    """Pour endpoints HTMX/API: renvoie (template_html, 200) si refusé, sinon None.
    Toutes les permissions listées doivent être vraies (ET logique).
    HTMX traite mieux les 200 avec contenu HTML qu'un 403.
    """
    user = getattr(g, 'current_user', None)
    if not _has_perm('can_access_admin'):
        return (render_template('access_denied.html', reason="Accès à l'administration requis", current_user=user), 200)
    for p in perm_attrs:
        if not _has_perm(p):
            return (render_template('access_denied.html', reason=f"Permission '{p}' requise", current_user=user), 200)
    return None


def _deny_access(reason: str):
    """Retourne un template d'accès refusé avec la raison spécifiée."""
    user = getattr(g, 'current_user', None)
    return render_template('access_denied.html', reason=reason, current_user=user), 200


def access_denied_page():
    """Page d'explication d'accès refusé."""
    user = getattr(g, 'current_user', None)
    return render_template('access_denied_full.html', current_user=user)


def auth_widget():
    """Widget d'authentification qui calcule les messages non lus."""
    from models import ConversationParticipant, ConversationMessage
    from sqlalchemy import or_
    from datetime import datetime

    # Calculer le nombre de messages non lus pour l'utilisateur connecté
    unread = 0
    has_messages = False
    user = getattr(g, 'current_user', None)
    if user and user.password_hash:
        try:
            parts = ConversationParticipant.query.filter_by(user_id=user.id).all()
            print(f"[WIDGET] User {user.username} has {len(parts)} conversation participations")

            # Vérifier si l'utilisateur a au moins des messages (participations aux conversations)
            has_messages = len(parts) > 0

            for p in parts:
                last_read = p.last_read_at or datetime.min
                # Pour les nouveaux participants (last_read_at=None), compter tous les messages sauf ceux de l'utilisateur
                if p.last_read_at is None:
                    count = ConversationMessage.query.filter(
                        ConversationMessage.conversation_id == p.conversation_id,
                        or_(ConversationMessage.sender_id.is_(None), ConversationMessage.sender_id != user.id)
                    ).count()
                    print(f"[WIDGET] Conversation {p.conversation_id}: NEW participant, messages={count}")
                else:
                    count = ConversationMessage.query.filter(
                        ConversationMessage.conversation_id == p.conversation_id,
                        ConversationMessage.created_at > last_read,
                        or_(ConversationMessage.sender_id.is_(None), ConversationMessage.sender_id != user.id)
                    ).count()
                    print(f"[WIDGET] Conversation {p.conversation_id}: last_read={p.last_read_at}, messages={count}")
                unread += count
            print(f"[WIDGET] Total unread for {user.username}: {unread}")
        except Exception as e:
            print(f"[WIDGET] Error calculating unread: {e}")
            unread = 0
            has_messages = False
    return render_template('auth_widget.html', unread_count=unread, has_messages=has_messages)


def load_current_user():
    """Charge l'utilisateur actuel depuis la session avant chaque requête."""
    user_id = session.get('user_id')
    g.current_user = db.session.get(User, user_id) if user_id else None


def inject_current_user():
    """Injecte l'utilisateur actuel dans tous les templates."""
    return { 'current_user': getattr(g, 'current_user', None) }
