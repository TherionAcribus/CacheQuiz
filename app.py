from flask import Flask, render_template, request, send_from_directory, redirect, session, g, url_for
from models import db, Question, BroadTheme, SpecificTheme, User, Country, ImageAsset, AnswerImageLink, QuizRuleSet, UserQuestionStat
from datetime import datetime
import os
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func, text
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///geocaching_quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB

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
            db.session.commit()
    except Exception:
        # Ne bloque pas l'app; pour autres SGBD, utiliser une migration Alembic
        db.session.rollback()

# ================== Gestion Session / Utilisateur ==================

@app.before_request
def load_current_user():
    user_id = session.get('user_id')
    g.current_user = User.query.get(user_id) if user_id else None


@app.context_processor
def inject_current_user():
    return { 'current_user': getattr(g, 'current_user', None) }


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
        # Créer un user sans mot de passe
        user = User(username=pseudo, display_name=pseudo, email=None, is_active=True)
        db.session.add(user)
        db.session.commit()
    session['user_id'] = user.id
    # Assurer que le widget reflète l'état connecté dans cette même réponse
    g.current_user = user
    return render_template('auth_widget.html')


@app.route('/auth/logout', methods=['POST'])
def logout():
    session.pop('user_id', None)
    # Assurer que le widget reflète l'état déconnecté dans cette même réponse
    g.current_user = None
    return render_template('auth_widget.html')


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
        display_name = (request.form.get('display_name') or '').strip() or username
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
            display_name=display_name,
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


# ================== Gestion des Images ==================

@app.route('/images')
def images_page():
    return render_template('images.html')


@app.route('/api/images')
def list_images_api():
    search = request.args.get('search', '').strip()
    query = ImageAsset.query
    if search:
        query = query.filter(ImageAsset.title.like(f'%{search}%'))
    images = query.order_by(ImageAsset.created_at.desc()).all()
    return render_template('images_list.html', images=images)


@app.route('/image/new')
def new_image():
    return render_template('image_form.html', image=None)


@app.route('/image/<int:image_id>/edit')
def edit_image(image_id: int):
    image = ImageAsset.query.get_or_404(image_id)
    return render_template('image_form.html', image=image)


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
        title = request.form.get('title', '').strip()
        alt_text = request.form.get('alt_text', '').strip()
        file = request.files.get('file')
        if not title:
            return "Titre requis", 400
        if not file:
            return "Fichier requis", 400

        filename = _secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        # Déduire l'unicité en cas de collision
        if os.path.exists(filepath):
            name, ext = os.path.splitext(filename)
            filename = f"{name}_{int(datetime.utcnow().timestamp())}{ext}"
            filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)

        file.save(filepath)
        size_bytes = os.path.getsize(filepath)
        mime_type = file.mimetype

        image = ImageAsset(title=title, filename=filename, mime_type=mime_type, size_bytes=size_bytes, alt_text=alt_text)
        db.session.add(image)
        db.session.commit()

        images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
        return render_template('images_list.html', images=images)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/image/<int:image_id>', methods=['POST', 'PUT'])
def update_image(image_id: int):
    try:
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
    """Page d'accueil avec la liste des questions"""
    return render_template('index.html')


@app.route('/questions')
def list_questions():
    """Retourner la liste des questions en HTML (pour HTMX)"""
    view = request.args.get('view', 'cards')
    sort_by = request.args.get('sort_by', 'updated_at')
    sort_order = request.args.get('sort_order', 'desc')

    base_query = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)

    questions = _apply_sorting(base_query, sort_by, sort_order).all()
    return render_template('questions_list.html', questions=questions, view=view, sort_by=sort_by, sort_order=sort_order)


@app.route('/question/new')
def new_question():
    """Formulaire pour créer une nouvelle question"""
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
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
    question = Question.query.get_or_404(question_id)
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
    return render_template('question_form.html', question=question, themes=themes, specific_themes=specific_themes, users=users, countries=countries, images=images)


@app.route('/api/question', methods=['POST'])
def create_question():
    """Créer une nouvelle question"""
    try:
        data = request.form
        
        # Traiter les réponses possibles
        possible_answers = []
        answer_images = []
        i = 1
        while f'answer_{i}' in data:
            answer = data.get(f'answer_{i}', '').strip()
            if answer:
                possible_answers.append(answer)
                # Lier éventuellement une image à cette réponse
                answer_image_id = data.get(f'answer_image_id_{i}', '').strip()
                if answer_image_id:
                    try:
                        answer_image_id_int = int(answer_image_id)
                        # On stockera via AnswerImageLink juste après création de la question
                        answer_images.append(str(answer_image_id_int))
                    except Exception:
                        pass
            i += 1
        
        question = Question(
            author_id=int(data.get('author_id')),
            question_text=data.get('question_text'),
            possible_answers='|||'.join(possible_answers),
            answer_images='|||'.join(answer_images),
            correct_answer=data.get('correct_answer'),
            detailed_answer=data.get('detailed_answer'),
            hint=data.get('hint'),
            source=data.get('source').strip() if data.get('source') else None,
            detailed_answer_image_id=int(data.get('detailed_answer_image_id')) if data.get('detailed_answer_image_id') else None,
            broad_theme_id=int(data.get('broad_theme_id')) if data.get('broad_theme_id') else None,
            specific_theme_id=int(data.get('specific_theme_id')) if data.get('specific_theme_id') else None,
            difficulty_level=int(data.get('difficulty_level', 1)),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None,
            is_published=data.get('is_published') == 'on'
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

        # Gérer les liens image->réponse (AnswerImageLink)
        idx = 1
        for token in answer_images:
            token = token.strip()
            if token.isdigit():
                db.session.add(AnswerImageLink(question_id=question.id, answer_index=idx, image_id=int(token)))
            idx += 1

        db.session.commit()
        
        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/question/<int:question_id>', methods=['PUT', 'POST'])
def update_question(question_id):
    """Mettre à jour une question existante"""
    try:
        question = Question.query.get_or_404(question_id)
        data = request.form
        
        # Traiter les réponses possibles
        possible_answers = []
        answer_images = []
        i = 1
        while f'answer_{i}' in data:
            answer = data.get(f'answer_{i}', '').strip()
            if answer:
                possible_answers.append(answer)
                answer_image_id = data.get(f'answer_image_id_{i}', '').strip()
                if answer_image_id:
                    answer_images.append(answer_image_id)
            i += 1
        
        # Mettre à jour les champs
        question.author_id = int(data.get('author_id'))
        question.question_text = data.get('question_text')
        question.possible_answers = '|||'.join(possible_answers)
        question.answer_images = '|||'.join(answer_images)
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
        idx = 1
        for token in answer_images:
            token = token.strip()
            if token.isdigit():
                db.session.add(AnswerImageLink(question_id=question.id, answer_index=idx, image_id=int(token)))
            idx += 1

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
        question = Question.query.get_or_404(question_id)
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
        question = Question.query.get_or_404(question_id)
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
            return query.order_by(User.display_name.asc().nulls_last())
        else:
            return query.order_by(User.display_name.desc().nulls_last())
    else:
        # Tri par défaut
        return query.order_by(Question.updated_at.desc())


@app.route('/api/questions/search')
def search_questions():
    """Rechercher des questions"""
    query_param = request.args.get('q', '').strip()
    view = request.args.get('view', 'cards')
    sort_by = request.args.get('sort_by', 'updated_at')
    sort_order = request.args.get('sort_order', 'desc')

    base_query = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)

    if query_param:
        base_query = base_query.filter(
            db.or_(
                Question.question_text.contains(query_param),
                User.display_name.contains(query_param),
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
                User.display_name.contains(query_param),
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
    return render_template('themes.html')


@app.route('/api/themes')
def list_themes():
    """Retourner la liste des thèmes en HTML (pour HTMX)"""
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('themes_list.html', themes=themes)


@app.route('/theme/new')
def new_theme():
    """Formulaire pour créer un nouveau thème"""
    return render_template('theme_form.html', theme=None)


@app.route('/theme/<int:theme_id>/edit')
def edit_theme(theme_id):
    """Formulaire pour éditer un thème"""
    theme = BroadTheme.query.get_or_404(theme_id)
    return render_template('theme_form.html', theme=theme)


@app.route('/api/theme', methods=['POST'])
def create_theme():
    """Créer un nouveau thème"""
    try:
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
    return render_template('specific_themes.html')


@app.route('/api/specific-themes')
def list_specific_themes():
    """Retourner la liste des sous-thèmes en HTML (pour HTMX)"""
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    return render_template('specific_themes_list.html', specific_themes=specific_themes)


@app.route('/specific-theme/new')
def new_specific_theme():
    """Formulaire pour créer un nouveau sous-thème"""
    broad_themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('specific_theme_form.html', specific_theme=None, broad_themes=broad_themes)


@app.route('/specific-theme/<int:specific_theme_id>/edit')
def edit_specific_theme(specific_theme_id):
    """Formulaire pour éditer un sous-thème"""
    specific_theme = SpecificTheme.query.get_or_404(specific_theme_id)
    broad_themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('specific_theme_form.html', specific_theme=specific_theme, broad_themes=broad_themes)


@app.route('/api/specific-theme', methods=['POST'])
def create_specific_theme():
    """Créer un nouveau sous-thème"""
    try:
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
    return render_template('users.html')


@app.route('/api/users')
def list_users():
    """Retourner la liste des utilisateurs en HTML (pour HTMX)"""
    users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
    return render_template('users_list.html', users=users)


@app.route('/user/new')
def new_user():
    """Formulaire pour créer un nouvel utilisateur"""
    return render_template('user_form.html', user=None)


@app.route('/user/<int:user_id>/edit')
def edit_user(user_id):
    """Formulaire pour éditer un utilisateur"""
    user = User.query.get_or_404(user_id)
    return render_template('user_form.html', user=user)


@app.route('/api/user', methods=['POST'])
def create_user():
    """Créer un nouvel utilisateur"""
    try:
        data = request.form

        user = User(
            username=data.get('username'),
            email=data.get('email') or None,
            display_name=data.get('display_name'),
            is_active=data.get('is_active') == 'on'
        )

        db.session.add(user)
        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/user/<int:user_id>', methods=['PUT', 'POST'])
def update_user(user_id):
    """Mettre à jour un utilisateur existant"""
    try:
        user = User.query.get_or_404(user_id)
        data = request.form

        # Mettre à jour les champs
        user.username = data.get('username')
        user.email = data.get('email') or None
        user.display_name = data.get('display_name')
        user.is_active = data.get('is_active') == 'on'

        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/user/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Désactiver un utilisateur (soft delete)"""
    try:
        user = User.query.get_or_404(user_id)

        # Vérifier si l'utilisateur a des questions
        question_count = user.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer cet utilisateur : {question_count} question(s) lui appartiennent encore.", 400

        # Soft delete : désactiver au lieu de supprimer
        user.is_active = False
        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


# ============ Routes pour la gestion des Pays ============

@app.route('/countries')
def countries():
    """Page de gestion des pays"""
    return render_template('countries.html')


@app.route('/api/countries')
def list_countries_api():
    """Retourner la liste des pays en HTML (pour HTMX)"""
    search = request.args.get('search', '')
    query = Country.query
    
    if search:
        query = query.filter(Country.name.like(f'%{search}%'))
    
    countries = query.order_by(Country.name).all()
    return render_template('countries_list.html', countries=countries)


@app.route('/country/new')
def new_country():
    """Formulaire pour créer un nouveau pays"""
    countries = Country.query.order_by(Country.name).all()
    return render_template('country_form.html', country=None, countries=countries)


@app.route('/country/<int:country_id>/edit')
def edit_country(country_id):
    """Formulaire pour éditer un pays"""
    country = Country.query.get_or_404(country_id)
    countries = Country.query.order_by(Country.name).all()
    return render_template('country_form.html', country=country, countries=countries)


@app.route('/api/country', methods=['POST'])
def create_country():
    """Créer un nouveau pays"""
    try:
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
    """Retourne une question aléatoire (selon filtres ou set de règles) pour le quiz."""
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

        query = Question.query.filter(Question.is_published.is_(True))
        query = _apply_quiz_filters(query, params)

        if history_ids:
            query = query.filter(~Question.id.in_(history_ids))

        # Exclure questions déjà vues par l'utilisateur connecté
        if getattr(g, 'current_user', None):
            seen_ids = [row.question_id for row in UserQuestionStat.query.with_entities(UserQuestionStat.question_id).filter_by(user_id=g.current_user.id).all()]
            if seen_ids:
                query = query.filter(~Question.id.in_(seen_ids))

        # Si on utilise un set de règles avec quotas par difficulté
        rule_set = None
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

        # SQLite: random(), PostgreSQL: RANDOM()
        question = query.order_by(db.func.random()).first()

        # Calculer la progression et le score total (stocké en session)
        total_questions = 0
        total_score = 0
        current_question_num = 0

        if rule_set:
            # Gestion du score en session (reset en début de session)
            score_session_key = f"quiz_score:{rule_set.slug}"
            if not history_raw:
                session[score_session_key] = 0
            total_score = int(session.get(score_session_key, 0) or 0)

            # Compter le nombre total de questions dans cette session
            history_ids = []
            if history_raw:
                for token in history_raw.split(','):
                    token = token.strip()
                    if token.isdigit():
                        history_ids.append(int(token))
            current_question_num = len(history_ids) + 1

            # Calculer le nombre total de questions selon les quotas
            if rule_set.get_questions_per_difficulty():
                qmap = rule_set.get_questions_per_difficulty()
                total_questions = sum(qmap.values())
            else:
                # Si pas de quotas, compter toutes les questions publiées
                total_questions = Question.query.filter(Question.is_published.is_(True)).count()

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

        question = Question.query.get_or_404(int(question_id_raw))
        correct_value = (question.correct_answer or '').strip()
        # Si pas de réponse (timer expiré ou non sélection), considérer comme faux
        is_correct = bool(selected_answer) and (selected_answer == correct_value)

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

        # Mettre à jour le score total en session uniquement si correct
        if rule_set:
            score_session_key = f"quiz_score:{rule_set.slug}"
            total_score_session = int(session.get(score_session_key, 0) or 0)
            if is_correct and score:
                total_score_session += int(score)
            session[score_session_key] = total_score_session

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
            # Nombre total de questions dans cette session
            if rule_set.get_questions_per_difficulty():
                qmap = rule_set.get_questions_per_difficulty()
                total_questions = sum(qmap.values())
            else:
                total_questions = Question.query.filter(Question.is_published.is_(True)).count()

            current_question_num = len(history_ids)

            # Score total depuis la session
            score_session_key = f"quiz_score:{rule_set.slug}"
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
    return render_template('quiz_rules.html')


@app.route('/api/quiz-rules')
def list_quiz_rules():
    """Retourner la liste des sets de règles en HTML (pour HTMX)"""
    rules = QuizRuleSet.query.order_by(QuizRuleSet.updated_at.desc()).all()
    return render_template('quiz_rules_list.html', rules=rules)


@app.route('/quiz-rule/new')
def new_quiz_rule():
    """Formulaire pour créer un nouveau set de règles"""
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
    return render_template('quiz_rule_form.html', rule=None, themes=themes, specific_themes=specific_themes, users=users)


@app.route('/quiz-rule/<int:rule_id>/edit')
def edit_quiz_rule(rule_id: int):
    """Formulaire pour éditer un set de règles existant"""
    rule = QuizRuleSet.query.get_or_404(rule_id)
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
    return render_template('quiz_rule_form.html', rule=rule, themes=themes, specific_themes=specific_themes, users=users)


@app.route('/api/quiz-rule', methods=['POST'])
def create_quiz_rule():
    """Créer un nouveau set de règles"""
    try:
        data = request.form

        name = (data.get('name') or '').strip()
        if not name:
            return "Nom requis", 400

        slug = (data.get('slug') or '').strip() or _slugify(name)

        rule = QuizRuleSet(
            name=name,
            slug=slug,
            description=(data.get('description') or '').strip() or None,
            comment=(data.get('comment') or '').strip() or None,
            is_active=(data.get('is_active') == 'on'),
            created_by_user_id=int(data.get('created_by_user_id')),
            timer_seconds=int(data.get('timer_seconds') or 30),
            use_all_broad_themes=(data.get('use_all_broad_themes') == 'on'),
            use_all_specific_themes=(data.get('use_all_specific_themes') == 'on'),
            scoring_base_points=int(data.get('scoring_base_points') or 1),
            scoring_difficulty_bonus_type=(data.get('scoring_difficulty_bonus_type') or 'none'),
            combo_bonus_enabled=(data.get('combo_bonus_enabled') == 'on'),
            combo_step=(int(data.get('combo_step')) if data.get('combo_step') else None),
            combo_bonus_points=(int(data.get('combo_bonus_points')) if data.get('combo_bonus_points') else None),
            perfect_quiz_bonus=int(data.get('perfect_quiz_bonus') or 0),
            intro_message=(data.get('intro_message') or '').strip() or None,
            success_message=(data.get('success_message') or '').strip() or None,
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

        if data.get('created_by_user_id') and data.get('created_by_user_id').isdigit():
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
        rule.intro_message = (data.get('intro_message') or '').strip() or None
        rule.success_message = (data.get('success_message') or '').strip() or None

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
        db.session.delete(rule)
        db.session.commit()
        rules = QuizRuleSet.query.order_by(QuizRuleSet.updated_at.desc()).all()
        return render_template('quiz_rules_list.html', rules=rules)
    except Exception as e:
        return f"Erreur: {str(e)}", 400

if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

