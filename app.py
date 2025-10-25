from flask import Flask, render_template, request, send_from_directory, redirect, session, g, url_for, make_response
from models import db, Question, BroadTheme, SpecificTheme, User, Country, ImageAsset, AnswerImageLink, QuizRuleSet, UserQuestionStat, Profile
from datetime import datetime
import random
import os
import re
import json
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func, text
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from unidecode import unidecode

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///geocaching_quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB
app.config['SOUNDS_FOLDER'] = os.path.join(os.getcwd(), 'ressources', 'sounds')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

# Créer les tables
with app.app_context():
    db.create_all()
    # Auto-migration légère pour SQLite: ajout des nouvelles colonnes de users si manquantes
    try:
        if db.engine.url.drivername.startswith('sqlite'):
            result = db.session.execute(text("PRAGMA table_info(users)"))
            existing_cols = {row[1] for row in result.fetchall()}
            # password_hash
            if 'password_hash' not in existing_cols:
                db.session.execute(text("ALTER TABLE users ADD COLUMN password_hash TEXT"))
            # is_admin (0/1)
            if 'is_admin' not in existing_cols:
                db.session.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN NOT NULL DEFAULT 0"))
            # preferences_json
            if 'preferences_json' not in existing_cols:
                db.session.execute(text("ALTER TABLE users ADD COLUMN preferences_json TEXT"))
            # profile_id (nullable)
            if 'profile_id' not in existing_cols:
                db.session.execute(text("ALTER TABLE users ADD COLUMN profile_id INTEGER"))
            db.session.commit()

            # Migration pour la table questions
            result_questions = db.session.execute(text("PRAGMA table_info(questions)"))
            existing_cols_questions = {row[1] for row in result_questions.fetchall()}
            # is_private (False par défaut = publique)
            if 'is_private' not in existing_cols_questions:
                db.session.execute(text("ALTER TABLE questions ADD COLUMN is_private BOOLEAN NOT NULL DEFAULT 0"))
            db.session.commit()
    except Exception:
        # Ne bloque pas l'app; pour autres SGBD, utiliser une migration Alembic
        db.session.rollback()

    # Seed de profils par défaut (idempotent)
    try:
        def ensure_profile(name: str, **perms):
            p = Profile.query.filter_by(name=name).first()
            if not p:
                p = Profile(name=name, **perms)
                db.session.add(p)
            else:
                # Mettre à jour si de nouveaux flags ajoutés
                for k, v in perms.items():
                    if hasattr(p, k):
                        setattr(p, k, v)
            return p

        # Administrateur: tous droits
        ensure_profile(
            'Administrateur',
            description="Accès complet à l'administration",
            can_access_admin=True,
            can_create_question=True,
            can_update_delete_own_question=True,
            can_update_delete_any_question=True,
            can_create_rule=True,
            can_update_delete_own_rule=True,
            can_update_delete_any_rule=True,
            can_manage_users=True,
            can_manage_profiles=True,
        )

        # Éditeur: gère ses contenus, accès admin
        ensure_profile(
            'Éditeur',
            description="Peut gérer ses questions et ses règles",
            can_access_admin=True,
            can_create_question=True,
            can_update_delete_own_question=True,
            can_update_delete_any_question=False,
            can_create_rule=True,
            can_update_delete_own_rule=True,
            can_update_delete_any_rule=False,
            can_manage_users=False,
            can_manage_profiles=False,
        )

        # Modérateur: peut modifier/supprimer globalement, mais ne gère pas utilisateurs/profils
        ensure_profile(
            'Modérateur',
            description="Peut modérer toutes les questions et règles",
            can_access_admin=True,
            can_create_question=False,
            can_update_delete_own_question=True,
            can_update_delete_any_question=True,
            can_create_rule=False,
            can_update_delete_own_rule=True,
            can_update_delete_any_rule=True,
            can_manage_users=False,
            can_manage_profiles=False,
        )

        # Lecteur: accès admin en lecture (listes), pas de création ni modification
        ensure_profile(
            'Lecteur',
            description="Accès en lecture seule à l'administration",
            can_access_admin=False,  # Pas d'accès admin pour les lecteurs
            can_create_question=False,
            can_update_delete_own_question=False,
            can_update_delete_any_question=False,
            can_create_rule=False,
            can_update_delete_own_rule=False,
            can_update_delete_any_rule=False,
            can_manage_users=False,
            can_manage_profiles=False,
        )

        db.session.commit()
    except Exception:
        db.session.rollback()

# ================== Gestion Session / Utilisateur ==================

@app.before_request
def load_current_user():
    user_id = session.get('user_id')
    g.current_user = User.query.get(user_id) if user_id else None


@app.context_processor
def inject_current_user():
    return { 'current_user': getattr(g, 'current_user', None) }


# ================== Helpers Permissions ==================

def _has_perm(perm_attr: str) -> bool:
    user = getattr(g, 'current_user', None)
    return bool(user and user.has_perm(perm_attr))


@app.route('/access-denied')
def access_denied_page():
    """Page d'explication d'accès refusé."""
    user = getattr(g, 'current_user', None)
    return render_template('access_denied_full.html', current_user=user)


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


@app.route('/auth/widget')
def auth_widget():
    return render_template('auth_widget.html')


@app.route('/auth/quick-login', methods=['POST'])
def quick_login():
    pseudo = (request.form.get('pseudo') or '').strip()
    if not pseudo:
        return "Pseudo requis", 400

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
        resp.headers['HX-Redirect'] = url_for('play_quiz')
        return resp
    elif user.password_hash:
        # Si l'utilisateur a un mot de passe, afficher le formulaire de connexion avec pseudo pré-rempli
        return render_template('auth_widget.html', login_username=pseudo, show_password_form=True)
    else:
        # Utilisateur existant sans mot de passe, connexion directe
        session['user_id'] = user.id
        # Assurer que le widget reflète l'état connecté dans cette même réponse
        g.current_user = user
        resp = make_response('')
        resp.headers['HX-Redirect'] = url_for('play_quiz')
        return resp


@app.route('/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    # Assurer que le widget reflète l'état déconnecté dans cette même réponse
    g.current_user = None
    resp = make_response('')
    resp.headers['HX-Redirect'] = url_for('index')
    return resp


@app.route('/auth/widget-login', methods=['POST'])
def widget_login():
    """Connexion depuis le widget avec pseudo + mot de passe."""
    username = (request.form.get('username') or '').strip()
    password = (request.form.get('password') or '').strip()

    if not username or not password:
        return render_template('auth_widget.html', login_username=username, show_password_form=True, error_message="Pseudo et mot de passe requis")

    user = User.query.filter_by(username=username).first()
    if not user or not user.password_hash or not check_password_hash(user.password_hash, password):
        return render_template('auth_widget.html', login_username=username, show_password_form=True, error_message="Identifiants invalides")

    session['user_id'] = user.id
    # Assurer que le widget reflète l'état connecté dans cette même réponse
    g.current_user = user
    resp = make_response('')
    resp.headers['HX-Redirect'] = url_for('play_quiz')
    return resp


@app.route('/auth/upgrade-account', methods=['POST'])
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


@app.route('/login', methods=['GET', 'POST'])
def login_page():
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


@app.route('/register', methods=['GET', 'POST'])
def register_page():
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


def _get_token_serializer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='password-reset')


@app.route('/forgot-password', methods=['GET', 'POST'])
def forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        if not email:
            return render_template('forgot_password.html', error="Email requis")
        user = User.query.filter_by(email=email).first()
        # Toujours indiquer que l'email a été envoyé pour éviter la fuite d'existence
        if user:
            s = _get_token_serializer()
            token = s.dumps({'uid': user.id})
            # Ici on simule l'envoi: on rend la page avec le lien (POC). En prod, envoyer un email.
            reset_link = url_for('reset_password', token=token, _external=True)
            return render_template('forgot_password.html', info="Un email a été envoyé.", reset_link=reset_link)
        return render_template('forgot_password.html', info="Un email a été envoyé.")
    return render_template('forgot_password.html')


@app.route('/reset-password/<token>', methods=['GET', 'POST'])
def reset_password(token):
    s = _get_token_serializer()
    try:
        data = s.loads(token, max_age=3600)  # 1h
        user_id = data.get('uid')
    except SignatureExpired:
        return render_template('reset_password.html', error="Lien expiré"), 400
    except BadSignature:
        return render_template('reset_password.html', error="Lien invalide"), 400

    user = User.query.get_or_404(user_id)
    if request.method == 'POST':
        password = (request.form.get('password') or '').strip()
        password2 = (request.form.get('password2') or '').strip()
        if not password:
            return render_template('reset_password.html', error="Mot de passe requis", token=token)
        if password != password2:
            return render_template('reset_password.html', error="Les mots de passe ne correspondent pas", token=token)
        user.password_hash = generate_password_hash(password)
        db.session.commit()
        return redirect(url_for('login_page'))
    return render_template('reset_password.html', token=token)


@app.route('/me')
def me_page():
    if not g.current_user:
        return redirect(url_for('play_quiz'))
    # Dernières 20 réponses
    stats = (UserQuestionStat.query
             .filter_by(user_id=g.current_user.id)
             .order_by(UserQuestionStat.last_answered_at.desc())
             .limit(20)
             .all())
    # Totaux globaux
    totals = (db.session.query(
                    func.coalesce(func.sum(UserQuestionStat.times_answered), 0),
                    func.coalesce(func.sum(UserQuestionStat.success_count), 0)
               )
               .filter(UserQuestionStat.user_id == g.current_user.id)
               .one())
    total_answers = totals[0] or 0
    total_success = totals[1] or 0
    return render_template('me.html', stats=stats, total_answers=total_answers, total_success=total_success)
# ================== Fichiers uploadés (serveur) ==================

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ================== Fichiers sons ==================
@app.route('/sounds/<path:filename>')
def sounds_file(filename):
    # Sert les fichiers audio depuis ressources/sounds
    return send_from_directory(app.config['SOUNDS_FOLDER'], filename)


# ================== Gestion des Images ==================

@app.route('/images')
def images_page():
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('images.html')


@app.route('/api/images')
def list_images_api():
    denied = _ensure_perm_api()
    if denied:
        return denied
    search = request.args.get('search', '').strip()
    query = ImageAsset.query
    if search:
        query = query.filter(ImageAsset.title.like(f'%{search}%'))
    images = query.order_by(ImageAsset.created_at.desc()).all()
    return render_template('images_list.html', images=images)


@app.route('/api/images/json')
def list_images_json():
    """Retourne la liste des images au format JSON pour les selects"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    search = request.args.get('search', '').strip()
    query = ImageAsset.query
    if search:
        query = query.filter(ImageAsset.title.like(f'%{search}%'))
    images = query.order_by(ImageAsset.title).all()
    return [{
        'id': img.id,
        'title': img.title,
        'filename': img.filename,
        'alt_text': img.alt_text
    } for img in images]


@app.route('/image/new')
def new_image():
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    embedded = request.args.get('embedded') in ('1', 'true', 'yes')
    select_id = request.args.get('select_id') or ''
    return render_template('image_form.html', image=None, embedded=embedded, select_id=select_id)


@app.route('/image/<int:image_id>/edit')
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


@app.route('/api/image', methods=['POST'])
def create_image():
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        title = request.form.get('title', '').strip()
        alt_text = request.form.get('alt_text', '').strip()
        file = request.files.get('file')
        if not title:
            return "Titre requis", 400
        if not file:
            return "Fichier requis", 400

        filename = _secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Déduire l'unicité en cas de collision physique
        if os.path.exists(filepath):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Vérifier l'unicité du nom de fichier dans la base de données
        base_filename = filename
        counter = 1
        while ImageAsset.query.filter_by(filename=filename).first() is not None:
            name, ext = os.path.splitext(base_filename)
            filename = f"{name}_{counter}{ext}"
            counter += 1

        # Mettre à jour le filepath si le nom a changé
        if filename != base_filename:
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        file.save(filepath)
        size_bytes = os.path.getsize(filepath)
        mime_type = file.mimetype

        image = ImageAsset(title=title, filename=filename, mime_type=mime_type, size_bytes=size_bytes, alt_text=alt_text)
        db.session.add(image)
        db.session.commit()

        # Si formulaire embarqué (modale au-dessus d'une autre modale): renvoyer JSON
        if request.form.get('embedded') in ('1', 'true', 'yes') or request.args.get('embedded') in ('1', 'true', 'yes'):
            return {
                'created_image': {
                    'id': image.id,
                    'title': image.title,
                    'filename': image.filename,
                    'alt_text': image.alt_text
                },
                'select_id': request.form.get('select_id') or request.args.get('select_id') or ''
            }

        images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
        return render_template('images_list.html', images=images)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/image/<int:image_id>', methods=['POST', 'PUT'])
def update_image(image_id: int):
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        image = ImageAsset.query.get_or_404(image_id)
        title = request.form.get('title', '').strip()
        alt_text = request.form.get('alt_text', '').strip()
        file = request.files.get('file')

        if title:
            image.title = title
        image.alt_text = alt_text

        if file:
            filename = _secure_filename(file.filename)
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


@app.route('/api/image/<int:image_id>', methods=['DELETE'])
def delete_image(image_id: int):
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


@app.route('/')
def index():
    """Accueil: page publique si non connecté, sinon page de jeu."""
    if getattr(g, 'current_user', None):
        return redirect(url_for('play_quiz'))
    return render_template('home_public.html')


@app.route('/admin')
def admin_page():
    """Page d'administration avec la liste des questions"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('index.html')


@app.route('/questions')
def list_questions():
    """Retourner la liste des questions en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    view = request.args.get('view', 'cards')
    sort_by = request.args.get('sort_by', 'updated_at')
    sort_order = request.args.get('sort_order', 'desc')

    base_query = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)

    questions = _apply_sorting(base_query, sort_by, sort_order).all()
    return render_template('questions_list.html', questions=questions, view=view, sort_by=sort_by, sort_order=sort_order)


@app.route('/question/new')
def new_question():
    """Formulaire pour créer une nouvelle question"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_create_question'):
        return _deny_access("Permission 'can_create_question' requise")
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    images = ImageAsset.query.order_by(ImageAsset.title).all()
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
    return render_template('question_form.html', question=None, themes=themes, specific_themes=specific_themes, users=users, countries=countries, images=images)


@app.route('/question/<int:question_id>')
def view_question(question_id):
    """Voir les détails d'une question"""
    question = Question.query.get_or_404(question_id)
    return render_template('question_detail.html', question=question)


@app.route('/question/<int:question_id>/edit')
def edit_question(question_id):
    """Formulaire pour éditer une question"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    question = Question.query.get_or_404(question_id)
    can_any = _has_perm('can_update_delete_any_question')
    can_own = _has_perm('can_update_delete_own_question')
    if not (can_any or (can_own and getattr(g, 'current_user', None) and question.author_id == g.current_user.id)):
        user = getattr(g, 'current_user', None)
        return render_template('access_denied.html', reason="Permission 'can_update_delete_own_question' ou 'can_update_delete_any_question' requise", current_user=user), 200
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
    return render_template('question_form.html', question=question, themes=themes, specific_themes=specific_themes, users=users, countries=countries, images=images)


@app.route('/api/question', methods=['POST'])
def create_question():
    """Créer une nouvelle question"""
    try:
        denied = _ensure_perm_api('can_create_question')
        if denied:
            return denied
        data = request.form
        
        # Traiter les réponses possibles (en conservant l'index des réponses retenues)
        possible_answers = []
        answer_images_per_answer = []  # aligné sur possible_answers ('' si pas d'image)
        links_to_add = []  # liste de tuples (answer_index, image_id)
        i = 1
        current_index = 0
        while f'answer_{i}' in data:
            answer = (data.get(f'answer_{i}', '') or '').strip()
            answer_image_token = (data.get(f'answer_image_id_{i}', '') or '').strip()
            if answer or answer_image_token:
                current_index += 1
                possible_answers.append(answer)
                if answer_image_token.isdigit():
                    image_id_int = int(answer_image_token)
                    answer_images_per_answer.append(str(image_id_int))
                    links_to_add.append((current_index, image_id_int))
                else:
                    answer_images_per_answer.append('')
            i += 1
        
        # Attribuer l'auteur en fonction des droits
        if _has_perm('can_update_delete_any_question') and (data.get('author_id') or '').isdigit():
            author_id = int(data.get('author_id'))
        else:
            author_id = g.current_user.id if getattr(g, 'current_user', None) else None

        question = Question(
            author_id=author_id,
            question_text=data.get('question_text'),
            possible_answers='|||'.join(possible_answers),
            answer_images='|||'.join(answer_images_per_answer),
            correct_answer=data.get('correct_answer'),
            detailed_answer=data.get('detailed_answer'),
            hint=data.get('hint'),
            source=data.get('source').strip() if data.get('source') else None,
            detailed_answer_image_id=int(data.get('detailed_answer_image_id')) if data.get('detailed_answer_image_id') else None,
            broad_theme_id=int(data.get('broad_theme_id')) if data.get('broad_theme_id') else None,
            specific_theme_id=int(data.get('specific_theme_id')) if data.get('specific_theme_id') else None,
            difficulty_level=int(data.get('difficulty_level', 1)),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None,
            is_published=data.get('is_published') == 'on',
            is_private=data.get('is_private') == 'on'
        )
        
        # Gérer les pays (relation many-to-many)
        country_ids = request.form.getlist('countries')
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            question.countries = countries

        # Gérer l'image de la question (relation many-to-many, une seule image)
        question_image_id = request.form.get('question_image_id')
        if question_image_id:
            try:
                img = ImageAsset.query.get(int(question_image_id))
                if img:
                    question.images = [img]
            except ValueError:
                pass
        else:
            question.images = []
        
        db.session.add(question)
        db.session.flush()

        # Gérer les liens image->réponse (AnswerImageLink) avec index correct
        for answer_index, image_id in links_to_add:
            db.session.add(AnswerImageLink(question_id=question.id, answer_index=answer_index, image_id=image_id))

        db.session.commit()
        
        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/question/<int:question_id>', methods=['GET'])
def get_question_detail(question_id):
    """Récupérer le détail complet d'une question"""
    try:
        question = Question.query.get(question_id)
        if not question:
            return {'error': 'Question non trouvée'}, 404
        
        return question.to_dict()
    
    except Exception as e:
        print(f"Erreur lors de la récupération de la question {question_id}: {e}")
        return {'error': str(e)}, 500


@app.route('/api/question/<int:question_id>', methods=['PUT', 'POST'])
def update_question(question_id):
    """Mettre à jour une question existante"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        question = Question.query.get_or_404(question_id)
        can_any = _has_perm('can_update_delete_any_question')
        can_own = _has_perm('can_update_delete_own_question')
        if not (can_any or (can_own and getattr(g, 'current_user', None) and question.author_id == g.current_user.id)):
            return _deny_access("Permission 'can_update_delete_own_question' ou 'can_update_delete_any_question' requise")
        data = request.form
        
        # Traiter les réponses possibles (en conservant l'index des réponses retenues)
        possible_answers = []
        answer_images_per_answer = []  # aligné sur possible_answers ('' si pas d'image)
        links_to_add = []  # liste de tuples (answer_index, image_id)
        i = 1
        current_index = 0
        while f'answer_{i}' in data:
            answer = (data.get(f'answer_{i}', '') or '').strip()
            answer_image_token = (data.get(f'answer_image_id_{i}', '') or '').strip()
            if answer or answer_image_token:
                current_index += 1
                possible_answers.append(answer)
                if answer_image_token.isdigit():
                    image_id_int = int(answer_image_token)
                    answer_images_per_answer.append(str(image_id_int))
                    links_to_add.append((current_index, image_id_int))
                else:
                    answer_images_per_answer.append('')
            i += 1
        
        # Mettre à jour les champs
        # Changer l'auteur uniquement avec le droit global
        if can_any and (data.get('author_id') or '').isdigit():
            question.author_id = int(data.get('author_id'))
        question.question_text = data.get('question_text')
        question.possible_answers = '|||'.join(possible_answers)
        question.answer_images = '|||'.join(answer_images_per_answer)
        question.correct_answer = data.get('correct_answer')
        question.detailed_answer = data.get('detailed_answer')
        question.hint = data.get('hint')
        question.source = data.get('source').strip() if data.get('source') else None
        question.detailed_answer_image_id = int(data.get('detailed_answer_image_id')) if data.get('detailed_answer_image_id') else None
        question.broad_theme_id = int(data.get('broad_theme_id')) if data.get('broad_theme_id') else None
        question.specific_theme_id = int(data.get('specific_theme_id')) if data.get('specific_theme_id') else None
        question.difficulty_level = int(data.get('difficulty_level', 1))
        question.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        question.is_published = data.get('is_published') == 'on'
        question.is_private = data.get('is_private') == 'on'
        question.updated_at = datetime.utcnow()
        
        # Gérer les pays (relation many-to-many)
        country_ids = request.form.getlist('countries')
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            question.countries = countries
        else:
            question.countries = []

        # Gérer l'image de la question (relation many-to-many, une seule image)
        question_image_id = request.form.get('question_image_id')
        if question_image_id:
            try:
                img = ImageAsset.query.get(int(question_image_id))
                if img:
                    question.images = [img]
            except ValueError:
                pass
        else:
            question.images = []
        
        # Réinitialiser les liens image->réponse
        AnswerImageLink.query.filter_by(question_id=question.id).delete()
        db.session.flush()
        for answer_index, image_id in links_to_add:
            db.session.add(AnswerImageLink(question_id=question.id, answer_index=answer_index, image_id=image_id))

        db.session.commit()
        
        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/question/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    """Supprimer une question"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        question = Question.query.get_or_404(question_id)
        can_any = _has_perm('can_update_delete_any_question')
        can_own = _has_perm('can_update_delete_own_question')
        if not (can_any or (can_own and getattr(g, 'current_user', None) and question.author_id == g.current_user.id)):
            return _deny_access("Permission 'can_update_delete_own_question' ou 'can_update_delete_any_question' requise")
        db.session.delete(question)
        db.session.commit()

        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/question/<int:question_id>/toggle-status', methods=['POST'])
def toggle_question_status(question_id):
    """Changer le statut de publication d'une question"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        question = Question.query.get_or_404(question_id)
        can_any = _has_perm('can_update_delete_any_question')
        can_own = _has_perm('can_update_delete_own_question')
        if not (can_any or (can_own and getattr(g, 'current_user', None) and question.author_id == g.current_user.id)):
            return _deny_access("Permission 'can_update_delete_own_question' ou 'can_update_delete_any_question' requise")
        question.is_published = not question.is_published
        question.updated_at = datetime.utcnow()
        db.session.commit()

        # Retourner uniquement le contenu de la cellule statut mis à jour
        return render_template('question_status_cell.html', question=question)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def _apply_sorting(query, sort_by, sort_order):
    """Appliquer le tri à la requête selon les paramètres donnés"""
    if sort_by == 'question_text':
        if sort_order == 'asc':
            return query.order_by(Question.question_text.asc())
        else:
            return query.order_by(Question.question_text.desc())
    elif sort_by == 'broad_theme':
        if sort_order == 'asc':
            return query.order_by(BroadTheme.name.asc().nulls_last())
        else:
            return query.order_by(BroadTheme.name.desc().nulls_last())
    elif sort_by == 'specific_theme':
        if sort_order == 'asc':
            return query.order_by(SpecificTheme.name.asc().nulls_last())
        else:
            return query.order_by(SpecificTheme.name.desc().nulls_last())
    elif sort_by == 'difficulty_level':
        if sort_order == 'asc':
            return query.order_by(Question.difficulty_level.asc())
        else:
            return query.order_by(Question.difficulty_level.desc())
    elif sort_by == 'is_published':
        if sort_order == 'asc':
            return query.order_by(Question.is_published.asc())
        else:
            return query.order_by(Question.is_published.desc())
    elif sort_by == 'created_at':
        if sort_order == 'asc':
            return query.order_by(Question.created_at.asc())
        else:
            return query.order_by(Question.created_at.desc())
    elif sort_by == 'author':
        if sort_order == 'asc':
            return query.order_by(User.username.asc().nulls_last())
        else:
            return query.order_by(User.username.desc().nulls_last())
    else:
        # Tri par défaut
        return query.order_by(Question.updated_at.desc())


@app.route('/api/questions/search')
def search_questions():
    """Rechercher des questions"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    query_param = request.args.get('q', '').strip()
    view = request.args.get('view', 'cards')
    sort_by = request.args.get('sort_by', 'updated_at')
    sort_order = request.args.get('sort_order', 'desc')

    base_query = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)

    if query_param:
        base_query = base_query.filter(
            db.or_(
                Question.question_text.contains(query_param),
                User.username.contains(query_param),
                User.username.contains(query_param),
                BroadTheme.name.contains(query_param),
                SpecificTheme.name.contains(query_param)
            )
        )

    questions = _apply_sorting(base_query, sort_by, sort_order).all()

    return render_template('questions_list.html', questions=questions, view=view, sort_by=sort_by, sort_order=sort_order)


@app.route('/api/questions/sort')
def sort_questions():
    """Trier les questions"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    view = request.args.get('view', 'cards')
    sort_by = request.args.get('sort_by', 'updated_at')
    query_param = request.args.get('q', '').strip()

    # Déterminer l'ordre de tri : si on clique sur la même colonne, on inverse l'ordre
    current_sort_by = request.args.get('current_sort_by', '')
    current_sort_order = request.args.get('current_sort_order', 'desc')

    if sort_by == current_sort_by:
        # Même colonne, on inverse l'ordre
        sort_order = 'asc' if current_sort_order == 'desc' else 'desc'
    else:
        # Nouvelle colonne, on commence par ascendant
        sort_order = 'asc'

    base_query = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)

    if query_param:
        base_query = base_query.filter(
            db.or_(
                Question.question_text.contains(query_param),
                User.username.contains(query_param),
                User.username.contains(query_param),
                BroadTheme.name.contains(query_param),
                SpecificTheme.name.contains(query_param)
            )
        )

    questions = _apply_sorting(base_query, sort_by, sort_order).all()

    return render_template('questions_list.html', questions=questions, view=view, sort_by=sort_by, sort_order=sort_order)


# ===== Routes pour les thèmes =====

@app.route('/themes')
def themes_page():
    """Page de gestion des thèmes"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('themes.html')


@app.route('/api/themes')
def list_themes():
    """Retourner la liste des thèmes en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('themes_list.html', themes=themes)


@app.route('/theme/new')
def new_theme():
    """Formulaire pour créer un nouveau thème"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('theme_form.html', theme=None)


@app.route('/theme/<int:theme_id>/edit')
def edit_theme(theme_id):
    """Formulaire pour éditer un thème"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    theme = BroadTheme.query.get_or_404(theme_id)
    return render_template('theme_form.html', theme=theme)


@app.route('/api/theme', methods=['POST'])
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
        
        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_list.html', themes=themes)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/theme/<int:theme_id>', methods=['PUT', 'POST'])
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
        return render_template('themes_list.html', themes=themes)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/theme/<int:theme_id>', methods=['DELETE'])
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
        return render_template('themes_list.html', themes=themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


# ===== Routes pour les sous-thèmes =====

@app.route('/specific-themes')
def specific_themes_page():
    """Page de gestion des sous-thèmes"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('specific_themes.html')


@app.route('/api/specific-themes')
def list_specific_themes():
    """Retourner la liste des sous-thèmes en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    return render_template('specific_themes_list.html', specific_themes=specific_themes)


@app.route('/specific-theme/new')
def new_specific_theme():
    """Formulaire pour créer un nouveau sous-thème"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    broad_themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('specific_theme_form.html', specific_theme=None, broad_themes=broad_themes)


@app.route('/specific-theme/<int:specific_theme_id>/edit')
def edit_specific_theme(specific_theme_id):
    """Formulaire pour éditer un sous-thème"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    specific_theme = SpecificTheme.query.get_or_404(specific_theme_id)
    broad_themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('specific_theme_form.html', specific_theme=specific_theme, broad_themes=broad_themes)


@app.route('/api/specific-theme', methods=['POST'])
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

        # Retourner la liste mise à jour
        specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
        return render_template('specific_themes_list.html', specific_themes=specific_themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/specific-theme/<int:specific_theme_id>', methods=['PUT', 'POST'])
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
        specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
        return render_template('specific_themes_list.html', specific_themes=specific_themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/specific-theme/<int:specific_theme_id>', methods=['DELETE'])
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
        specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
        return render_template('specific_themes_list.html', specific_themes=specific_themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/specific-themes/for-theme/')
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


# ===== Routes pour les utilisateurs =====

@app.route('/users')
def users_page():
    """Page de gestion des utilisateurs"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_users'):
        return redirect(url_for('play_quiz'))
    return render_template('users.html')


@app.route('/api/users')
def list_users():
    """Retourner la liste des utilisateurs en HTML (pour HTMX)"""
    denied = _ensure_perm_api('can_manage_users')
    if denied:
        return denied
    users = User.query.filter_by(is_active=True).order_by(User.username).all()
    return render_template('users_list.html', users=users)


@app.route('/user/new')
def new_user():
    """Formulaire pour créer un nouvel utilisateur"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_users'):
        return _deny_access("Permission 'can_manage_users' requise")
    profiles = Profile.query.order_by(Profile.name).all()
    return render_template('user_form.html', user=None, profiles=profiles)


@app.route('/user/<int:user_id>/edit')
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


@app.route('/api/user', methods=['POST'])
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


@app.route('/api/user/<int:user_id>', methods=['PUT', 'POST'])
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


@app.route('/api/user/<int:user_id>', methods=['DELETE'])
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


# ===== Routes pour les profils (permissions) =====

@app.route('/profiles')
def profiles_page():
    """Page de gestion des profils"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_profiles'):
        return redirect(url_for('play_quiz'))
    return render_template('profiles.html')


@app.route('/api/profiles')
def list_profiles():
    """Retourner la liste des profils en HTML (pour HTMX)"""
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied
    profiles = Profile.query.order_by(Profile.name).all()
    return render_template('profiles_list.html', profiles=profiles)


@app.route('/profile/new')
def new_profile():
    """Formulaire pour créer un nouveau profil"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_profiles'):
        return _deny_access("Permission 'can_manage_profiles' requise")
    return render_template('profile_form.html', profile=None)


@app.route('/profile/<int:profile_id>/edit')
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


@app.route('/api/profile', methods=['POST'])
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


@app.route('/api/profile/<int:profile_id>', methods=['PUT', 'POST'])
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


@app.route('/api/profile/<int:profile_id>', methods=['DELETE'])
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


# ============ Routes pour la gestion des Pays ============

@app.route('/countries')
def countries():
    """Page de gestion des pays"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('countries.html')


@app.route('/api/countries')
def list_countries_api():
    """Retourner la liste des pays en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    search = request.args.get('search', '')
    query = Country.query
    
    if search:
        query = query.filter(Country.name.like(f'%{search}%'))
    
    countries = query.order_by(Country.name).all()
    return render_template('countries_list.html', countries=countries)


@app.route('/country/new')
def new_country():
    """Formulaire pour créer un nouveau pays"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    countries = Country.query.order_by(Country.name).all()
    return render_template('country_form.html', country=None, countries=countries)


@app.route('/country/<int:country_id>/edit')
def edit_country(country_id):
    """Formulaire pour éditer un pays"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    country = Country.query.get_or_404(country_id)
    countries = Country.query.order_by(Country.name).all()
    return render_template('country_form.html', country=country, countries=countries)


@app.route('/api/country', methods=['POST'])
def create_country():
    """Créer un nouveau pays"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        data = request.form
        
        country = Country(
            name=data.get('name'),
            code=data.get('code'),
            flag=data.get('flag'),
            language=data.get('language', 'fr'),
            description=data.get('description'),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None
        )
        
        db.session.add(country)
        db.session.commit()
        
        # Retourner la liste mise à jour
        countries = Country.query.order_by(Country.name).all()
        return render_template('countries_list.html', countries=countries)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/country/<int:country_id>', methods=['PUT', 'POST'])
def update_country(country_id):
    """Mettre à jour un pays existant"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        country = Country.query.get_or_404(country_id)
        data = request.form
        
        # Mettre à jour les champs
        country.name = data.get('name')
        country.code = data.get('code')
        country.flag = data.get('flag')
        country.language = data.get('language', 'fr')
        country.description = data.get('description')
        country.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        country.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Retourner la liste mise à jour
        countries = Country.query.order_by(Country.name).all()
        return render_template('countries_list.html', countries=countries)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/country/<int:country_id>', methods=['DELETE'])
def delete_country(country_id):
    """Supprimer un pays"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        country = Country.query.get_or_404(country_id)
        
        # Vérifier si le pays est utilisé dans des questions
        question_count = country.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer ce pays : {question_count} question(s) l'utilisent encore.", 400
        
        db.session.delete(country)
        db.session.commit()
        
        countries = Country.query.order_by(Country.name).all()
        return render_template('countries_list.html', countries=countries)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


# ============ Interface de Quiz (Jouer) ============

@app.route('/quiz/<slug>')
def play_quiz_with_rules(slug: str):
    """Redirige vers la page de jeu avec un set de règles prédéfini."""
    return redirect(f'/play?rule_set={slug}')

def _apply_quiz_filters(query, params):
    """Appliquer les filtres du quiz (thèmes, pays, difficulté) au query de base."""
    rule_set_slug = (params.get('rule_set') or '').strip()
    if rule_set_slug:
        # Appliquer les règles du set
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
        if rule_set:
            # Difficultés autorisées
            allowed_diffs = rule_set.get_allowed_difficulties()
            if allowed_diffs:
                query = query.filter(Question.difficulty_level.in_(allowed_diffs))

            # Thèmes larges
            if not rule_set.use_all_broad_themes and rule_set.allowed_broad_themes:
                theme_ids = [t.id for t in rule_set.allowed_broad_themes]
                query = query.filter(Question.broad_theme_id.in_(theme_ids))

            # Sous-thèmes
            if not rule_set.use_all_specific_themes and rule_set.allowed_specific_themes:
                sub_theme_ids = [st.id for st in rule_set.allowed_specific_themes]
                query = query.filter(Question.specific_theme_id.in_(sub_theme_ids))

            # Note: pas de filtre pays pour l'instant dans les sets de règles
    else:
        # Mode manuel - appliquer les filtres classiques
        broad_theme_id = (params.get('broad_theme_id') or '').strip()
        if broad_theme_id.isdigit():
            query = query.filter(Question.broad_theme_id == int(broad_theme_id))

        specific_theme_id = (params.get('specific_theme_id') or '').strip()
        if specific_theme_id.isdigit():
            query = query.filter(Question.specific_theme_id == int(specific_theme_id))

        country_id = (params.get('country_id') or '').strip()
        if country_id.isdigit():
            query = query.filter(Question.countries.any(Country.id == int(country_id)))

        difficulty_level = (params.get('difficulty_level') or '').strip()
        if difficulty_level.isdigit():
            query = query.filter(Question.difficulty_level == int(difficulty_level))

    return query


def _interleave_round_robin(lists_by_difficulty):
    """Intercale les listes de questions par difficulté (round-robin) pour varier l'ordre.
    Entrée: dict[int,list[int]]
    Sortie: list[int]
    """
    # Convertir en liste de listes en conservant un ordre stable des clés
    difficulties = sorted(lists_by_difficulty.keys())
    buckets = [list(lists_by_difficulty[d]) for d in difficulties if lists_by_difficulty.get(d)]
    result = []
    # Tant qu'il reste des éléments dans au moins un bucket
    while any(buckets):
        next_buckets = []
        for bucket in buckets:
            if bucket:
                result.append(bucket.pop(0))
            # garder le bucket s'il reste des éléments
            if bucket:
                next_buckets.append(bucket)
        buckets = next_buckets
    return result


def _quiz_session_keys(rule_set_slug: str):
    """Construit des clés de session isolées par utilisateur et par set.
    Retourne (playlist_key, index_key, score_key, correct_key, user_id_str)
    """
    user_id_str = str(g.current_user.id) if getattr(g, 'current_user', None) else 'anon'
    prefix = f"{user_id_str}:{rule_set_slug}"
    playlist_key = f"quiz_playlist:{prefix}"
    index_key = f"quiz_playlist_index:{prefix}"
    score_key = f"quiz_score:{prefix}"
    correct_key = f"quiz_correct_answers:{prefix}"
    return playlist_key, index_key, score_key, correct_key, user_id_str


def _generate_quiz_playlist(rule_set: QuizRuleSet, current_user_id: int | None) -> list[int]:
    """Génère la playlist (liste d'IDs de questions) pour un quiz à longueur fixe.
    - En mode 'manual': réordonne la liste sélectionnée en mettant d'abord les non-vues.
    - En mode 'auto': respecte les quotas par difficulté, préférant non-vues puis complétant avec déjà vues.
    - Mélange intra-difficulté.
    """
    try:
        # Récupérer les IDs déjà vus par l'utilisateur (si connecté)
        seen_ids = set()
        if current_user_id:
            seen_ids = {row.question_id for row in UserQuestionStat.query.with_entities(UserQuestionStat.question_id).filter_by(user_id=current_user_id).all()}

        # Mode manuel: partir de la sélection explicite
        if rule_set.question_selection_mode == 'manual' and rule_set.selected_questions:
            selected = [q for q in rule_set.selected_questions if q.is_published]
            unseen = [q.id for q in selected if q.id not in seen_ids]
            seen = [q.id for q in selected if q.id in seen_ids]
            random.shuffle(unseen)
            random.shuffle(seen)
            playlist = unseen + seen
            return playlist

        # Mode auto: quotas par difficulté et filtres de thèmes
        qmap = rule_set.get_questions_per_difficulty() or {}
        allowed_diffs = rule_set.get_allowed_difficulties() or [1, 2, 3, 4, 5]

        # Construire la requête de base selon le set de règles
        base_params = {'rule_set': rule_set.slug}
        base_query = _apply_quiz_filters(Question.query.filter(Question.is_published.is_(True)), base_params)

        # Préparer par difficulté
        per_diff_ids: dict[int, list[int]] = {}
        for d in allowed_diffs:
            quota = int(qmap.get(str(d), 0) or 0)
            if quota <= 0:
                per_diff_ids[d] = []
                continue

            q_for_diff = base_query.filter(Question.difficulty_level == d)
            candidates = q_for_diff.with_entities(Question.id).all()
            candidate_ids = [row.id for row in candidates]

            # Séparer non-vues / vues
            unseen_ids = [qid for qid in candidate_ids if qid not in seen_ids]
            seen_ids_for_diff = [qid for qid in candidate_ids if qid in seen_ids]

            random.shuffle(unseen_ids)
            random.shuffle(seen_ids_for_diff)

            chosen = []
            # Prendre d'abord non-vues
            if unseen_ids:
                chosen.extend(unseen_ids[:quota])
            # Compléter si nécessaire avec vues
            if len(chosen) < quota and seen_ids_for_diff:
                remaining = quota - len(chosen)
                chosen.extend(seen_ids_for_diff[:remaining])

            per_diff_ids[d] = chosen

        # Intercaler pour varier
        playlist = _interleave_round_robin(per_diff_ids)
        # Log si quotas non respectés faute de pool suffisant
        expected_total = sum(int(qmap.get(str(d), 0) or 0) for d in allowed_diffs)
        if len(playlist) < expected_total:
            print(f"[QUIZ PLAYLIST] Avertissement: playlist incomplète ({len(playlist)}/{expected_total}). Pool insuffisant pour certains quotas.")

        return playlist
    except Exception as e:
        print(f"[QUIZ PLAYLIST] Erreur génération playlist: {e}")
        return []

@app.route('/play')
def play_quiz():
    """Page pour choisir un set de règles et jouer au quiz."""
    rule_set = None
    rule_set_slug = request.args.get('rule_set', '').strip()
    if rule_set_slug:
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

    # Récupérer tous les sets de règles actifs
    rule_sets = QuizRuleSet.query.filter_by(is_active=True).order_by(QuizRuleSet.name).all()

    return render_template('play.html', rule_sets=rule_sets, rule_set=rule_set)


@app.route('/api/quiz/next')
def next_quiz_question():
    """Retourne la prochaine question du quiz en consommant une playlist pré-générée.
    Si aucune playlist n'existe encore pour ce set, la génère et la stocke en session.
    """
    try:
        params = request.args
        rule_set_slug = (params.get('rule_set') or '').strip()
        history_raw = (params.get('history') or '').strip()
        history_ids = []
        if history_raw:
            for token in history_raw.split(','):
                token = token.strip()
                if token.isdigit():
                    history_ids.append(int(token))

        rule_set = None
        if rule_set_slug:
            rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
        
        # Mode playlist: construire/charger la playlist en session (clé par utilisateur)
        playlist_session_key = None
        playlist_index_key = None
        score_session_key = None
        correct_answers_session_key = None
        if rule_set:
            playlist_session_key, playlist_index_key, score_session_key, correct_answers_session_key, user_ns = _quiz_session_keys(rule_set.slug)

        question = None
        total_questions = 0
        if rule_set:
            # Si pas encore de playlist, la générer
            playlist: list[int] = session.get(playlist_session_key) or []
            # Si démarrage d'une nouvelle partie (history vide) OU playlist absente, régénérer
            if (not history_raw) or (not playlist):
                playlist = _generate_quiz_playlist(rule_set, g.current_user.id if getattr(g, 'current_user', None) else None)
                session[playlist_session_key] = playlist
                session[playlist_index_key] = 0
                # Reset score/correct pour ce namespace utilisateur+set
                session[score_session_key] = 0
                session[correct_answers_session_key] = 0
                print(f"[QUIZ PLAYLIST] Générée (reset={not bool(history_raw)}) pour user={user_ns} set='{rule_set.slug}' (len={len(playlist)}): {playlist}")

            total_questions = len(playlist)
            index = int(session.get(playlist_index_key, 0) or 0)

            # Si terminé: fin du quiz
            if index >= total_questions:
                # Récupérer le nombre de bonnes réponses depuis la session
                total_correct_answers = int(session.get(correct_answers_session_key, 0) or 0)
                total_score = int(session.get(score_session_key, 0) or 0)
                return render_template(
                    'quiz_final.html',
                    rule_set=rule_set,
                    total_questions=total_questions,
                    total_score=total_score,
                    total_correct_answers=total_correct_answers,
                    history=history_raw or ''
                )

            # Charger la prochaine question via l'ID de la playlist
            next_question_id = playlist[index]
            question = Question.query.options(
                db.joinedload(Question.images),
                db.joinedload(Question.detailed_answer_image),
                db.joinedload(Question.answer_image_links).joinedload(AnswerImageLink.image)
            ).get(next_question_id)
        else:
            # Mode sans set explicite: fallback à l'aléatoire historique (comme avant)
            query = Question.query.filter(Question.is_published.is_(True))
            query = _apply_quiz_filters(query, params)
            if history_ids:
                query = query.filter(~Question.id.in_(history_ids))
            question = query.options(
                db.joinedload(Question.images),
                db.joinedload(Question.detailed_answer_image),
                db.joinedload(Question.answer_image_links).joinedload(AnswerImageLink.image)
            ).order_by(db.func.random()).first()

        # Debug logging
        print(f"[QUIZ NEXT] Rule set: {rule_set_slug}, History: {history_raw}")
        print(f"[QUIZ NEXT] Selected question ID: {question.id if question else 'None'}")
        print(f"[QUIZ NEXT] Question difficulty: {question.difficulty_level if question else 'N/A'}")

        # Calculer la progression et le score total (stocké en session)
        total_score = 0
        current_question_num = 0

        if rule_set:
            # Gestion du score en session (reset en début de session)
            if not history_raw:
                # Note: la playlist réinitialise déjà score/correct au moment de la génération
                session[score_session_key] = session.get(score_session_key, 0) or 0
                session[correct_answers_session_key] = session.get(correct_answers_session_key, 0) or 0
            total_score = int(session.get(score_session_key, 0) or 0)

            # Progression basée sur la playlist
            playlist = session.get(playlist_session_key) or []
            index = int(session.get(playlist_index_key, 0) or 0)
            # Affichage utilisateur: index courant (1-based)
            current_question_num = min(index + 1, len(playlist)) if playlist else 1
            total_questions = len(playlist)

        return render_template('quiz_question.html',
                             question=question,
                             history=history_raw,
                             rule_set=rule_set,
                             current_question_num=current_question_num,
                             total_questions=total_questions,
                             total_score=total_score)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


def _calculate_score(rule_set, question, is_correct, history_questions):
    """Calcule le score selon les règles du set."""
    if not rule_set or not is_correct:
        return 0

    score = rule_set.scoring_base_points

    # Bonus selon difficulté
    if rule_set.scoring_difficulty_bonus_type == 'add':
        bonus_map = rule_set.get_difficulty_bonus_map()
        bonus = bonus_map.get(str(question.difficulty_level), 0)
        score += bonus
    elif rule_set.scoring_difficulty_bonus_type == 'mult':
        coeff_map = rule_set.get_difficulty_bonus_map()
        coeff = coeff_map.get(str(question.difficulty_level), 1.0)
        score = int(score * coeff)

    # Bonus de combo
    if rule_set.combo_bonus_enabled and rule_set.combo_step and rule_set.combo_bonus_points:
        # Compter les bonnes réponses consécutives à la fin
        consecutive_correct = 0
        for q in reversed(history_questions):
            if q.success_count > q.times_answered - q.success_count:  # Simplifié: majorité de succès
                consecutive_correct += 1
            else:
                break
        combo_count = consecutive_correct // rule_set.combo_step
        score += combo_count * rule_set.combo_bonus_points

    return score


@app.route('/api/debug/quiz-questions')
def debug_quiz_questions():
    """Route de debug pour afficher toutes les questions disponibles pour un quiz."""
    try:
        params = request.args
        rule_set_slug = (params.get('rule_set') or '').strip()
        history_raw = (params.get('history') or '').strip()
        history_ids = []
        if history_raw:
            for token in history_raw.split(','):
                token = token.strip()
                if token.isdigit():
                    history_ids.append(int(token))

        # Construire la requête identique à /api/quiz/next
        query = Question.query.filter(Question.is_published.is_(True))
        query = _apply_quiz_filters(query, params)

        if history_ids:
            query = query.filter(~Question.id.in_(history_ids))

        # Exclure questions déjà vues par l'utilisateur connecté
        if getattr(g, 'current_user', None):
            seen_ids = [row.question_id for row in UserQuestionStat.query.with_entities(UserQuestionStat.question_id).filter_by(user_id=g.current_user.id).all()]
            if seen_ids:
                query = query.filter(~Question.id.in_(seen_ids))

        # Appliquer la logique de set de règles si présent
        rule_set = None
        selected_diff = None
        if rule_set_slug:
            rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

        if rule_set and rule_set.get_questions_per_difficulty():
            # Logique de quotas par difficulté
            qmap = rule_set.get_questions_per_difficulty()
            allowed_diffs = rule_set.get_allowed_difficulties() or [1, 2, 3, 4, 5]

            # Compter les questions déjà posées par difficulté dans cette session
            history_questions = []
            if history_ids:
                history_questions = Question.query.filter(Question.id.in_(history_ids)).all()

            diff_counts = {d: sum(1 for q in history_questions if q.difficulty_level == d) for d in allowed_diffs}

            # Trouver les difficultés qui n'ont pas atteint leur quota
            available_diffs = []
            for d in allowed_diffs:
                max_q = qmap.get(str(d), 0)
                current_q = diff_counts.get(d, 0)
                if current_q < max_q:
                    available_diffs.append(d)

            if available_diffs:
                # Trier les difficultés par ordre croissant (1, 2, 3, 4, 5)
                available_diffs_sorted = sorted(available_diffs)
                # Sélectionner la difficulté la plus basse disponible
                selected_diff = available_diffs_sorted[0]
                query = query.filter(Question.difficulty_level == selected_diff)

        # Récupérer toutes les questions disponibles (sans random)
        questions = query.options(
            db.joinedload(Question.broad_theme),
            db.joinedload(Question.specific_theme),
            db.joinedload(Question.countries)
        ).order_by(Question.id).all()

        # Préparer les données de debug
        debug_data = {
            'rule_set': rule_set.name if rule_set else None,
            'rule_set_slug': rule_set_slug,
            'history_ids': history_ids,
            'selected_difficulty': selected_diff,
            'total_available_questions': len(questions),
            'questions': []
        }

        for q in questions:
            question_data = {
                'id': q.id,
                'question_text': q.question_text[:100] + '...' if len(q.question_text) > 100 else q.question_text,
                'difficulty_level': q.difficulty_level,
                'correct_answer': q.correct_answer,
                'broad_theme': q.broad_theme.name if q.broad_theme else None,
                'specific_theme': q.specific_theme.name if q.specific_theme else None,
                'countries': [c.name for c in q.countries] if q.countries else [],
                'times_answered': q.times_answered,
                'success_count': q.success_count
            }
            debug_data['questions'].append(question_data)

        # Afficher aussi dans la console du serveur
        print(f"\n=== DEBUG QUIZ QUESTIONS ===")
        print(f"Rule set: {debug_data['rule_set']} ({rule_set_slug})")
        print(f"History IDs: {history_ids}")
        print(f"Selected difficulty: {selected_diff}")
        print(f"Total available questions: {len(questions)}")
        print(f"Questions: {[q['id'] for q in debug_data['questions']]}")
        print("===========================\n")

        return debug_data

    except Exception as e:
        return {'error': str(e)}, 400


@app.route('/api/quiz/answer', methods=['POST'])
def submit_quiz_answer():
    """Valider la réponse de l'utilisateur, mettre à jour les stats et retourner le résultat."""
    try:
        question_id_raw = (request.form.get('question_id') or '').strip()
        selected_answer = (request.form.get('selected_answer') or '').strip()
        history_raw = (request.form.get('history') or '').strip()
        rule_set_slug = (request.form.get('rule_set') or '').strip()
        is_timeout = bool((request.form.get('timeout') or '').strip())

        if not question_id_raw.isdigit():
            return "Identifiant de question invalide", 400

        question = Question.query.options(
            db.joinedload(Question.images),
            db.joinedload(Question.detailed_answer_image),
            db.joinedload(Question.answer_image_links).joinedload(AnswerImageLink.image)
        ).get_or_404(int(question_id_raw))
        correct_value = (question.correct_answer or '').strip()
        # Si pas de réponse (timer expiré ou non sélection), considérer comme faux
        is_correct = bool(selected_answer) and (selected_answer == correct_value)

        # Debug logging
        print(f"[QUIZ ANSWER] Question ID: {question_id_raw}, Selected: '{selected_answer}', Correct: '{correct_value}', Is correct: {is_correct}")

        # Charger le set de règles si spécifié
        rule_set = None
        if rule_set_slug:
            rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

        # Calculer le score selon les règles
        score = 0
        if rule_set:
            # Récupérer l'historique complet pour le calcul du combo
            history_ids = []
            if history_raw:
                for token in history_raw.split(','):
                    token = token.strip()
                    if token.isdigit():
                        history_ids.append(int(token))
            history_questions = Question.query.filter(Question.id.in_(history_ids)).all() if history_ids else []
            score = _calculate_score(rule_set, question, is_correct, history_questions)

        # Mettre à jour les statistiques globales de la question
        question.times_answered = (question.times_answered or 0) + 1
        if is_correct:
            question.success_count = (question.success_count or 0) + 1
        question.updated_at = datetime.utcnow()

        # Mettre à jour les statistiques utilisateur-question
        if getattr(g, 'current_user', None):
            stat = UserQuestionStat.query.filter_by(user_id=g.current_user.id, question_id=question.id).first()
            if not stat:
                stat = UserQuestionStat(user_id=g.current_user.id, question_id=question.id)
                db.session.add(stat)
            stat.times_answered = (stat.times_answered or 0) + 1
            if is_correct:
                stat.success_count = (stat.success_count or 0) + 1
            stat.last_selected_answer = selected_answer
            stat.last_is_correct = is_correct
            stat.last_answered_at = datetime.utcnow()

        db.session.commit()

        # Mettre à jour le score total et le nombre de bonnes réponses en session (namespace user)
        if rule_set:
            _, _, score_session_key, correct_answers_session_key, _ = _quiz_session_keys(rule_set.slug)
            total_score_session = int(session.get(score_session_key, 0) or 0)
            if is_correct and score:
                total_score_session += int(score)
            session[score_session_key] = total_score_session

            # Compter les bonnes réponses
            total_correct_answers_session = int(session.get(correct_answers_session_key, 0) or 0)
            if is_correct:
                total_correct_answers_session += 1
            session[correct_answers_session_key] = total_correct_answers_session

        # Mettre à jour la progression de playlist (si set de règles, namespace user)
        if rule_set:
            playlist_session_key, playlist_index_key, score_session_key, correct_answers_session_key, user_ns = _quiz_session_keys(rule_set.slug)
            index = int(session.get(playlist_index_key, 0) or 0)
            playlist = session.get(playlist_session_key) or []
            # Avancer l'index si la question correspond à l'élément courant
            if index < len(playlist) and playlist[index] == question.id:
                session[playlist_index_key] = index + 1

        # Mettre à jour l'historique côté client (ajouter la question actuelle)
        history_ids = []
        if history_raw:
            for token in history_raw.split(','):
                token = token.strip()
                if token.isdigit():
                    history_ids.append(int(token))
        if question.id not in history_ids:
            history_ids.append(question.id)
        next_history = ','.join(str(i) for i in history_ids)

        # Calculer la progression et le score total mis à jour
        total_questions = 0
        current_question_num = 0
        total_score = 0

        if rule_set:
            # Progression basée sur la playlist
            playlist_session_key, playlist_index_key, score_session_key, correct_answers_session_key, user_ns = _quiz_session_keys(rule_set.slug)
            index = int(session.get(playlist_index_key, 0) or 0)
            playlist = session.get(playlist_session_key) or []
            total_questions = len(playlist)
            current_question_num = min(index, total_questions)

            # Score total depuis la session
            score_session_key = score_session_key
            total_score = int(session.get(score_session_key, 0) or 0)

        return render_template(
            'quiz_result.html',
            question=question,
            is_correct=is_correct,
            selected=selected_answer,
            history=next_history,
            rule_set=rule_set,
            score=score,
            current_question_num=current_question_num,
            total_questions=total_questions,
            total_score=total_score,
            is_timeout=is_timeout
        )
    except Exception as e:
        return f"Erreur: {str(e)}", 400


# ============ Routes pour la gestion des règles du Quiz ============

def _slugify(value: str) -> str:
    value = (value or '').strip().lower()
    safe = []
    for ch in value:
        if ch.isalnum():
            safe.append(ch)
        elif ch in [' ', '-', '_']:
            safe.append('-')
    slug = ''.join(safe)
    while '--' in slug:
        slug = slug.replace('--', '-')
    return slug.strip('-')


@app.route('/quiz-rules')
def quiz_rules_page():
    """Page d'administration des ensembles de règles du quiz"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('quiz_rules.html')


@app.route('/api/quiz-rules')
def list_quiz_rules():
    """Retourner la liste des sets de règles en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    rules = QuizRuleSet.query.order_by(QuizRuleSet.updated_at.desc()).all()
    return render_template('quiz_rules_list.html', rules=rules)


def _load_quiz_rule_defaults():
    """Charger les valeurs par défaut depuis le fichier JSON"""
    defaults_path = os.path.join(os.path.dirname(__file__), 'config', 'quiz_rules_defaults.json')
    try:
        if os.path.exists(defaults_path):
            with open(defaults_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                return config.get('defaults', {})
    except Exception as e:
        print(f"Erreur lors du chargement des valeurs par défaut: {e}")
    
    # Valeurs par défaut en dur si le fichier n'existe pas
    return {
        'is_active': True,
        'timer_seconds': 30,
        'use_all_broad_themes': True,
        'use_all_specific_themes': True,
        'check_all_broad_themes': True,
        'check_all_specific_themes': True,
        'allowed_difficulties': [1, 2, 3, 4, 5],
        'questions_per_difficulty': {'1': 2, '2': 3, '3': 3, '4': 2, '5': 1},
        'scoring_base_points': 10,
        'scoring_difficulty_bonus_type': 'add',
        'difficulty_bonus_map': {'1': 0, '2': 5, '3': 10, '4': 15, '5': 20},
        'combo_bonus_enabled': True,
        'combo_step': 3,
        'combo_bonus_points': 5,
        'perfect_quiz_bonus': 50,
        'intro_message': 'Bonne chance ! 🍀',
        'success_message': 'Félicitations ! 🎉'
    }


@app.route('/quiz-rule/new')
def new_quiz_rule():
    """Formulaire pour créer un nouveau set de règles"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_create_rule'):
        return _deny_access("Permission 'can_create_rule' requise")
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    images = ImageAsset.query.order_by(ImageAsset.title).all()
    
    # Charger les valeurs par défaut
    defaults = _load_quiz_rule_defaults()
    print(f"Defaults chargés pour création: {defaults}")
    
    return render_template('quiz_rule_form.html', rule=None, themes=themes, specific_themes=specific_themes, images=images, defaults=defaults)


@app.route('/quiz-rule/<int:rule_id>/edit')
def edit_quiz_rule(rule_id: int):
    """Formulaire pour éditer un set de règles existant"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    rule = QuizRuleSet.query.get_or_404(rule_id)
    can_any = _has_perm('can_update_delete_any_rule')
    can_own = _has_perm('can_update_delete_own_rule')
    if not (can_any or (can_own and getattr(g, 'current_user', None) and rule.created_by_user_id == g.current_user.id)):
        return _deny_access("Permission 'can_update_delete_own_rule' ou 'can_update_delete_any_rule' requise")
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    images = ImageAsset.query.order_by(ImageAsset.title).all()
    return render_template('quiz_rule_form.html', rule=rule, themes=themes, specific_themes=specific_themes, images=images, defaults={})


@app.route('/api/quiz-rule', methods=['POST'])
def create_quiz_rule():
    """Créer un nouveau set de règles"""
    try:
        denied = _ensure_perm_api('can_create_rule')
        if denied:
            return denied
        data = request.form

        name = (data.get('name') or '').strip()
        if not name:
            return "Nom requis", 400

        slug = (data.get('slug') or '').strip() or _slugify(name)

        created_by_user_id = g.current_user.id if getattr(g, 'current_user', None) else None
        rule = QuizRuleSet(
            name=name,
            slug=slug,
            description=(data.get('description') or '').strip() or None,
            comment=(data.get('comment') or '').strip() or None,
            is_active=(data.get('is_active') == 'on'),
            created_by_user_id=created_by_user_id,
            timer_seconds=int(data.get('timer_seconds') or 30),
            use_all_broad_themes=(data.get('use_all_broad_themes') == 'on'),
            use_all_specific_themes=(data.get('use_all_specific_themes') == 'on'),
            scoring_base_points=int(data.get('scoring_base_points') or 1),
            scoring_difficulty_bonus_type=(data.get('scoring_difficulty_bonus_type') or 'none'),
            combo_bonus_enabled=(data.get('combo_bonus_enabled') == 'on'),
            combo_step=(int(data.get('combo_step')) if data.get('combo_step') else None),
            combo_bonus_points=(int(data.get('combo_bonus_points')) if data.get('combo_bonus_points') else None),
            perfect_quiz_bonus=int(data.get('perfect_quiz_bonus') or 0),
            min_correct_answers_to_win=int(data.get('min_correct_answers_to_win') or 0),
            intro_message=(data.get('intro_message') or '').strip() or None,
            success_message=(data.get('success_message') or '').strip() or None,
            failure_message=(data.get('failure_message') or '').strip() or None,
            intro_image_id=(int(data.get('intro_image_id')) if (data.get('intro_image_id') or '').isdigit() else None),
            success_image_id=(int(data.get('success_image_id')) if (data.get('success_image_id') or '').isdigit() else None),
            failure_image_id=(int(data.get('failure_image_id')) if (data.get('failure_image_id') or '').isdigit() else None),
        )

        # Difficultés autorisées
        difficulties = [int(x) for x in data.getlist('allowed_difficulties') if (x or '').isdigit()]
        rule.set_allowed_difficulties(difficulties)

        # Quotas par difficulté
        quotas = {}
        for d in range(1, 6):
            val = (data.get(f'questions_per_difficulty_{d}') or '').strip()
            if val.isdigit():
                quotas[str(d)] = int(val)
        rule.set_questions_per_difficulty(quotas)

        # Bonus selon difficulté
        bonus_map = {}
        for d in range(1, 6):
            raw = (data.get(f'difficulty_bonus_{d}') or '').strip()
            if raw:
                try:
                    bonus_map[str(d)] = float(raw)
                except Exception:
                    pass
        rule.set_difficulty_bonus_map(bonus_map)

        # Thèmes autorisés (si non tous)
        if not rule.use_all_broad_themes:
            ids = [int(x) for x in data.getlist('allowed_broad_theme_ids') if (x or '').isdigit()]
            if ids:
                rule.allowed_broad_themes = BroadTheme.query.filter(BroadTheme.id.in_(ids)).all()

        if not rule.use_all_specific_themes:
            ids = [int(x) for x in data.getlist('allowed_specific_theme_ids') if (x or '').isdigit()]
            if ids:
                rule.allowed_specific_themes = SpecificTheme.query.filter(SpecificTheme.id.in_(ids)).all()

        # Détection automatique du mode de sélection
        selected_question_ids = [int(x) for x in data.getlist('selected_question_ids') if (x or '').isdigit()]
        
        # Récupérer toutes les questions disponibles selon les critères
        available_question_ids = []
        if not rule.use_all_specific_themes and rule.allowed_specific_themes:
            specific_theme_ids = [st.id for st in rule.allowed_specific_themes]
        else:
            specific_theme_ids = [st.id for st in SpecificTheme.query.all()]
        
        if specific_theme_ids and difficulties:
            available_questions = Question.query.filter(
                Question.specific_theme_id.in_(specific_theme_ids),
                Question.difficulty_level.in_(difficulties)
            ).all()
            available_question_ids = [q.id for q in available_questions]
        
        # Déterminer le mode : si toutes les questions disponibles sont sélectionnées -> mode auto
        # sinon -> mode manuel
        if selected_question_ids and set(selected_question_ids) != set(available_question_ids):
            # Mode manuel : l'utilisateur a désélectionné des questions
            rule.question_selection_mode = 'manual'
            rule.selected_questions = Question.query.filter(Question.id.in_(selected_question_ids)).all()
        else:
            # Mode auto : toutes les questions sont sélectionnées
            rule.question_selection_mode = 'auto'
            rule.selected_questions = []  # Vider la liste en mode auto

        db.session.add(rule)
        db.session.commit()

        rules = QuizRuleSet.query.order_by(QuizRuleSet.updated_at.desc()).all()
        return render_template('quiz_rules_list.html', rules=rules)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/quiz-rule/<int:rule_id>', methods=['PUT', 'POST'])
def update_quiz_rule(rule_id: int):
    """Mettre à jour un set de règles existant"""
    try:
        rule = QuizRuleSet.query.get_or_404(rule_id)
        can_any = _has_perm('can_update_delete_any_rule')
        can_own = _has_perm('can_update_delete_own_rule')
        denied = _ensure_perm_api()
        if denied:
            return denied
        if not (can_any or (can_own and getattr(g, 'current_user', None) and rule.created_by_user_id == g.current_user.id)):
            return _deny_access("Permission 'can_update_delete_own_rule' ou 'can_update_delete_any_rule' requise")
        data = request.form

        name = (data.get('name') or '').strip()
        if name:
            rule.name = name

        slug = (data.get('slug') or '').strip()
        if slug:
            rule.slug = slug
        else:
            # si slug vide explicitement, régénérer à partir du nom
            rule.slug = _slugify(rule.name)

        rule.description = (data.get('description') or '').strip() or None
        rule.comment = (data.get('comment') or '').strip() or None
        rule.is_active = (data.get('is_active') == 'on')

        if can_any and data.get('created_by_user_id') and data.get('created_by_user_id').isdigit():
            rule.created_by_user_id = int(data.get('created_by_user_id'))

        rule.timer_seconds = int(data.get('timer_seconds') or rule.timer_seconds or 30)
        rule.use_all_broad_themes = (data.get('use_all_broad_themes') == 'on')
        rule.use_all_specific_themes = (data.get('use_all_specific_themes') == 'on')
        rule.scoring_base_points = int(data.get('scoring_base_points') or rule.scoring_base_points or 1)
        rule.scoring_difficulty_bonus_type = (data.get('scoring_difficulty_bonus_type') or rule.scoring_difficulty_bonus_type or 'none')
        rule.combo_bonus_enabled = (data.get('combo_bonus_enabled') == 'on')
        rule.combo_step = (int(data.get('combo_step')) if data.get('combo_step') else None)
        rule.combo_bonus_points = (int(data.get('combo_bonus_points')) if data.get('combo_bonus_points') else None)
        rule.perfect_quiz_bonus = int(data.get('perfect_quiz_bonus') or rule.perfect_quiz_bonus or 0)
        rule.min_correct_answers_to_win = int(data.get('min_correct_answers_to_win') or rule.min_correct_answers_to_win or 0)
        rule.intro_message = (data.get('intro_message') or '').strip() or None
        rule.success_message = (data.get('success_message') or '').strip() or None
        rule.failure_message = (data.get('failure_message') or '').strip() or None
        rule.intro_image_id = (int(data.get('intro_image_id')) if (data.get('intro_image_id') or '').isdigit() else None)
        rule.success_image_id = (int(data.get('success_image_id')) if (data.get('success_image_id') or '').isdigit() else None)
        rule.failure_image_id = (int(data.get('failure_image_id')) if (data.get('failure_image_id') or '').isdigit() else None)

        # Difficultés autorisées
        difficulties = [int(x) for x in data.getlist('allowed_difficulties') if (x or '').isdigit()]
        rule.set_allowed_difficulties(difficulties)

        # Quotas par difficulté
        quotas = {}
        for d in range(1, 6):
            val = (data.get(f'questions_per_difficulty_{d}') or '').strip()
            if val.isdigit():
                quotas[str(d)] = int(val)
        rule.set_questions_per_difficulty(quotas)

        # Bonus selon difficulté
        bonus_map = {}
        for d in range(1, 6):
            raw = (data.get(f'difficulty_bonus_{d}') or '').strip()
            if raw:
                try:
                    bonus_map[str(d)] = float(raw)
                except Exception:
                    pass
        rule.set_difficulty_bonus_map(bonus_map)

        # Thèmes autorisés (si non tous)
        if rule.use_all_broad_themes:
            rule.allowed_broad_themes = []
        else:
            ids = [int(x) for x in data.getlist('allowed_broad_theme_ids') if (x or '').isdigit()]
            rule.allowed_broad_themes = BroadTheme.query.filter(BroadTheme.id.in_(ids)).all() if ids else []

        if rule.use_all_specific_themes:
            rule.allowed_specific_themes = []
        else:
            ids = [int(x) for x in data.getlist('allowed_specific_theme_ids') if (x or '').isdigit()]
            rule.allowed_specific_themes = SpecificTheme.query.filter(SpecificTheme.id.in_(ids)).all() if ids else []

        # Détection automatique du mode de sélection
        selected_question_ids = [int(x) for x in data.getlist('selected_question_ids') if (x or '').isdigit()]
        
        # Récupérer toutes les questions disponibles selon les critères
        available_question_ids = []
        if not rule.use_all_specific_themes and rule.allowed_specific_themes:
            specific_theme_ids = [st.id for st in rule.allowed_specific_themes]
        else:
            specific_theme_ids = [st.id for st in SpecificTheme.query.all()]
        
        if specific_theme_ids and difficulties:
            available_questions = Question.query.filter(
                Question.specific_theme_id.in_(specific_theme_ids),
                Question.difficulty_level.in_(difficulties)
            ).all()
            available_question_ids = [q.id for q in available_questions]
        
        # Déterminer le mode : si toutes les questions disponibles sont sélectionnées -> mode auto
        # sinon -> mode manuel
        if selected_question_ids and set(selected_question_ids) != set(available_question_ids):
            # Mode manuel : l'utilisateur a désélectionné des questions
            rule.question_selection_mode = 'manual'
            rule.selected_questions = Question.query.filter(Question.id.in_(selected_question_ids)).all()
        else:
            # Mode auto : toutes les questions sont sélectionnées
            rule.question_selection_mode = 'auto'
            rule.selected_questions = []  # Vider la liste en mode auto

        rule.updated_at = datetime.utcnow()
        db.session.commit()

        rules = QuizRuleSet.query.order_by(QuizRuleSet.updated_at.desc()).all()
        return render_template('quiz_rules_list.html', rules=rules)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/quiz-rule/<int:rule_id>', methods=['DELETE'])
def delete_quiz_rule(rule_id: int):
    """Supprimer un set de règles"""
    try:
        rule = QuizRuleSet.query.get_or_404(rule_id)
        can_any = _has_perm('can_update_delete_any_rule')
        can_own = _has_perm('can_update_delete_own_rule')
        denied = _ensure_perm_api()
        if denied:
            return denied
        if not (can_any or (can_own and getattr(g, 'current_user', None) and rule.created_by_user_id == g.current_user.id)):
            return _deny_access("Permission 'can_update_delete_own_rule' ou 'can_update_delete_any_rule' requise")
        db.session.delete(rule)
        db.session.commit()
        rules = QuizRuleSet.query.order_by(QuizRuleSet.updated_at.desc()).all()
        return render_template('quiz_rules_list.html', rules=rules)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/quiz-rule/check-name', methods=['GET'])
def check_quiz_rule_name():
    """Vérifier si un nom de règle existe déjà"""
    name = request.args.get('name', '').strip()
    exclude_id = request.args.get('exclude_id')

    if not name:
        return ''

    # Normaliser le nom saisi (supprimer accents et convertir en minuscules)
    normalized_input = unidecode(name).lower()

    # Récupérer tous les noms existants et les normaliser
    existing_rules = QuizRuleSet.query.all()
    for rule in existing_rules:
        # Exclure la règle actuelle en édition
        if exclude_id and str(rule.id) == exclude_id:
            continue

        # Normaliser le nom existant
        normalized_existing = unidecode(rule.name).lower()

        # Vérifier si les noms normalisés correspondent
        if normalized_input == normalized_existing:
            return f'<span class="field-error">Le nom \'{name}\' existe déjà</span>'

    # Si aucun nom similaire n'est trouvé
    return f'<span style="color: #28a745; font-size: 0.875rem;">✓ Le nom \'{name}\' est disponible</span>'


@app.route('/api/quiz-rule/check-slug', methods=['GET'])
def check_quiz_rule_slug():
    """Vérifier si un slug de règle existe déjà"""
    slug = request.args.get('slug', '').strip()
    exclude_id = request.args.get('exclude_id')

    if not slug:
        return ''

    # Vérifier si le slug existe déjà
    query = QuizRuleSet.query.filter_by(slug=slug)
    if exclude_id and exclude_id.isdigit():
        query = query.filter(QuizRuleSet.id != int(exclude_id))

    exists = query.first() is not None

    if exists:
        return f'<span class="field-error">Le slug \'{slug}\' existe déjà</span>'
    else:
        return f'<span style="color: #28a745; font-size: 0.875rem;">✓ Le slug \'{slug}\' est disponible</span>'


@app.route('/api/quiz-rule/count-questions', methods=['GET'])
def count_questions_for_rule():
    """Compter le nombre de questions disponibles selon les critères sélectionnés"""
    specific_theme_ids = request.args.getlist('specific_theme_ids[]', type=int)
    difficulty_levels = request.args.getlist('difficulty_levels[]', type=int)

    if not specific_theme_ids or not difficulty_levels:
        return {'count': 0, 'message': 'Sélectionnez au moins un sous-thème et une difficulté'}

    try:
        # Compter les questions qui correspondent aux critères
        query = Question.query.filter(
            Question.specific_theme_id.in_(specific_theme_ids),
            Question.difficulty_level.in_(difficulty_levels)
        )

        count = query.count()

        if count == 0:
            message = 'Aucune question ne correspond à ces critères'
        elif count == 1:
            message = '1 question disponible'
        else:
            message = f'{count} questions disponibles'

        return {'count': count, 'message': message}

    except Exception as e:
        print(f"Erreur lors du comptage des questions: {e}")
        return {'count': 0, 'message': 'Erreur lors du calcul'}


@app.route('/api/quiz-rule/get-questions', methods=['GET'])
def get_questions_for_selection():
    """Récupérer les questions disponibles pour la sélection manuelle"""
    specific_theme_ids = request.args.getlist('specific_theme_ids[]', type=int)
    difficulty_levels = request.args.getlist('difficulty_levels[]', type=int)

    if not specific_theme_ids or not difficulty_levels:
        return {'questions': [], 'message': 'Sélectionnez au moins un sous-thème et une difficulté'}

    try:
        # Récupérer les questions qui correspondent aux critères
        questions = Question.query.filter(
            Question.specific_theme_id.in_(specific_theme_ids),
            Question.difficulty_level.in_(difficulty_levels)
        ).order_by(Question.specific_theme_id, Question.difficulty_level, Question.id).all()

        questions_data = []
        for q in questions:
            questions_data.append({
                'id': q.id,
                'question_text': q.question_text[:200] + '...' if len(q.question_text) > 200 else q.question_text,
                'broad_theme_name': q.theme.name if q.theme else None,
                'specific_theme_name': q.specific_theme_obj.name if q.specific_theme_obj else None,
                'difficulty_level': q.difficulty_level
            })

        return {'questions': questions_data, 'count': len(questions_data)}

    except Exception as e:
        print(f"Erreur lors de la récupération des questions: {e}")
        return {'questions': [], 'error': str(e)}


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

