from flask import Flask, render_template, request, send_from_directory, redirect, session, g, url_for, make_response, flash
from models import db, Question, BroadTheme, SpecificTheme, User, Country, ImageAsset, AnswerImageLink, QuizRuleSet, UserQuestionStat, UserQuizSession, QuestionAnswerStat, Profile, Conversation, ConversationParticipant, ConversationMessage, QuestionReport, ContactMessage, Keyword, QuizShareLink, SavedQuestion
from datetime import datetime
import random
import os
import re
import json
import uuid
from werkzeug.security import check_password_hash, generate_password_hash
from sqlalchemy import func, text, or_
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
import io
try:
    from PIL import Image
except Exception:
    Image = None
from unidecode import unidecode
from email_utils import send_email_optional
from config import config
from auth import quick_login, logout, widget_login, upgrade_account, login_page, register_page, _has_perm, _ensure_admin_page_redirect, _ensure_perm_api, _deny_access
from admin_images import images_page, list_images_api, list_images_json, images_gallery_fragment, new_image, edit_image, create_image, update_image, delete_image
from admin_export import export_page, export_download
from admin_themes import list_themes, list_themes_json, list_subthemes_json, list_authors_json, list_difficulties_json, new_theme, edit_theme, create_theme, update_theme, delete_theme, specific_themes_page, list_specific_themes, new_specific_theme, edit_specific_theme, create_specific_theme, update_specific_theme, delete_specific_theme, get_specific_themes_for_broad_theme, themes_unified_page
from admin_analyse import analysis_page, heatmap_data, question_stats_page
from admin_questions import new_question, view_question, edit_question, create_question, get_question_detail, update_question, delete_question, toggle_question_status, search_questions, sort_questions, _apply_sorting
from admin_keywords import list_keywords_json, create_keyword
from admin_countries import countries, list_countries_api, new_country, edit_country, create_country, update_country, delete_country
from admin_profiles import profiles_page, list_profiles, new_profile, edit_profile, create_profile, update_profile, delete_profile
from admin_users import users_page, list_users, new_user, edit_user, create_user, update_user, delete_user
from quiz_sharing import create_quiz_share_link, show_share_page, track_share_click, _parse_bool_param

app = Flask(__name__)

# Configuration selon l'environnement
config_name = os.environ.get('FLASK_ENV') or 'development'
app.config.from_object(config[config_name])
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

        # Créer un administrateur par défaut si aucun admin n'existe
        admin_profile = Profile.query.filter_by(name='Administrateur').first()
        if admin_profile:
            admin_count = User.query.filter_by(profile_id=admin_profile.id, is_active=True).count()
            if admin_count == 0:
                # Créer l'admin par défaut
                from werkzeug.security import generate_password_hash
                default_admin = User(
                    username='admin',
                    email='admin@geocaching-quiz.com',
                    password_hash=generate_password_hash('admin123'),
                    is_active=True,
                    profile_id=admin_profile.id
                )
                db.session.add(default_admin)
                db.session.commit()
                print("[INIT] Administrateur par défaut créé: username='admin', password='admin123'")

    except Exception as e:
        db.session.rollback()
        print(f"[WARN] Erreur lors de l'initialisation des données: {e}")

# ================== Gestion Session / Utilisateur ==================

@app.before_request
def load_current_user():
    user_id = session.get('user_id')
    g.current_user = db.session.get(User, user_id) if user_id else None


@app.context_processor
def inject_current_user():
    return { 'current_user': getattr(g, 'current_user', None) }




# ================== Helpers Permissions ==================

@app.route('/access-denied')
def access_denied_page():
    """Page d'explication d'accès refusé."""
    user = getattr(g, 'current_user', None)
    return render_template('access_denied_full.html', current_user=user)




@app.route('/auth/widget')
def auth_widget():
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




# Auth routes
app.add_url_rule('/auth/quick-login', 'quick_login', quick_login, methods=['POST'])
app.add_url_rule('/auth/logout', 'logout', logout, methods=['POST'])
app.add_url_rule('/auth/widget-login', 'widget_login', widget_login, methods=['POST'])
app.add_url_rule('/auth/upgrade-account', 'upgrade_account', upgrade_account, methods=['POST'])
app.add_url_rule('/login', 'login_page', login_page, methods=['GET', 'POST'])
app.add_url_rule('/register', 'register_page', register_page, methods=['GET', 'POST'])

# Image routes
app.add_url_rule('/images', 'images_page', images_page)
app.add_url_rule('/api/images', 'list_images_api', list_images_api)
app.add_url_rule('/api/images/json', 'list_images_json', list_images_json)
app.add_url_rule('/api/images/gallery', 'images_gallery_fragment', images_gallery_fragment)
app.add_url_rule('/image/new', 'new_image', new_image)
app.add_url_rule('/image/<int:image_id>/edit', 'edit_image', edit_image, methods=['GET'])

# Wrapper functions for image routes that need app parameter
def create_image_wrapper():
    return create_image(app)

def update_image_wrapper(image_id):
    return update_image(image_id, app)

def delete_image_wrapper(image_id):
    return delete_image(image_id, app)

app.add_url_rule('/api/image', 'create_image', create_image_wrapper, methods=['POST'])
app.add_url_rule('/api/image/<int:image_id>', 'update_image', update_image_wrapper, methods=['POST', 'PUT'])
app.add_url_rule('/api/image/<int:image_id>', 'delete_image', delete_image_wrapper, methods=['DELETE'])

# Export routes
app.add_url_rule('/export', 'export_page', export_page)
app.add_url_rule('/api/export/download', 'export_download', export_download)

# Theme routes
app.add_url_rule('/api/themes', 'list_themes', list_themes)
app.add_url_rule('/api/themes/json', 'list_themes_json', list_themes_json)
app.add_url_rule('/api/subthemes/json', 'list_subthemes_json', list_subthemes_json)
app.add_url_rule('/api/authors/json', 'list_authors_json', list_authors_json)
app.add_url_rule('/api/difficulties/json', 'list_difficulties_json', list_difficulties_json)
app.add_url_rule('/theme/new', 'new_theme', new_theme)
app.add_url_rule('/theme/<int:theme_id>/edit', 'edit_theme', edit_theme, methods=['GET'])
app.add_url_rule('/api/theme', 'create_theme', create_theme, methods=['POST'])
app.add_url_rule('/api/theme/<int:theme_id>', 'update_theme', update_theme, methods=['POST', 'PUT'])
app.add_url_rule('/api/theme/<int:theme_id>', 'delete_theme', delete_theme, methods=['DELETE'])
app.add_url_rule('/specific-themes', 'specific_themes_page', specific_themes_page)
app.add_url_rule('/api/specific-themes', 'list_specific_themes', list_specific_themes)
app.add_url_rule('/specific-theme/new', 'new_specific_theme', new_specific_theme)
app.add_url_rule('/specific-theme/<int:specific_theme_id>/edit', 'edit_specific_theme', edit_specific_theme, methods=['GET'])
app.add_url_rule('/api/specific-theme', 'create_specific_theme', create_specific_theme, methods=['POST'])
app.add_url_rule('/api/specific-theme/<int:specific_theme_id>', 'update_specific_theme', update_specific_theme, methods=['POST', 'PUT'])
app.add_url_rule('/api/specific-theme/<int:specific_theme_id>', 'delete_specific_theme', delete_specific_theme, methods=['DELETE'])
app.add_url_rule('/api/specific-themes/for-theme/', 'get_specific_themes_for_broad_theme', get_specific_themes_for_broad_theme)
app.add_url_rule('/themes', 'themes_unified_page', themes_unified_page)

# Analysis routes
app.add_url_rule('/analysis', 'analysis_page', analysis_page)
app.add_url_rule('/api/heatmap', 'heatmap_data', heatmap_data)
app.add_url_rule('/question/<int:question_id>/stats', 'question_stats_page', question_stats_page)

# Question routes
app.add_url_rule('/question/new', 'new_question', new_question)
app.add_url_rule('/question/<int:question_id>', 'view_question', view_question)
app.add_url_rule('/question/<int:question_id>/edit', 'edit_question', edit_question, methods=['GET'])
app.add_url_rule('/api/question', 'create_question', create_question, methods=['POST'])
app.add_url_rule('/api/question/<int:question_id>', 'get_question_detail', get_question_detail, methods=['GET'])
app.add_url_rule('/api/question/<int:question_id>', 'update_question', update_question, methods=['POST', 'PUT'])
app.add_url_rule('/api/question/<int:question_id>', 'delete_question', delete_question, methods=['DELETE'])
app.add_url_rule('/api/question/<int:question_id>/toggle-status', 'toggle_question_status', toggle_question_status, methods=['POST'])
app.add_url_rule('/api/questions/search', 'search_questions', search_questions)
app.add_url_rule('/api/questions/sort', 'sort_questions', sort_questions)

# Keywords routes
app.add_url_rule('/api/keywords/json', 'list_keywords_json', list_keywords_json)
app.add_url_rule('/api/keyword', 'create_keyword', create_keyword, methods=['POST'])

# Countries routes
app.add_url_rule('/countries', 'countries', countries)
app.add_url_rule('/api/countries', 'list_countries_api', list_countries_api)
app.add_url_rule('/country/new', 'new_country', new_country)
app.add_url_rule('/country/<int:country_id>/edit', 'edit_country', edit_country, methods=['GET'])
app.add_url_rule('/api/country', 'create_country', create_country, methods=['POST'])
app.add_url_rule('/api/country/<int:country_id>', 'update_country', update_country, methods=['POST', 'PUT'])
app.add_url_rule('/api/country/<int:country_id>', 'delete_country', delete_country, methods=['DELETE'])

# Profiles routes
app.add_url_rule('/profiles', 'profiles_page', profiles_page)
app.add_url_rule('/api/profiles', 'list_profiles', list_profiles)
app.add_url_rule('/profile/new', 'new_profile', new_profile)
app.add_url_rule('/profile/<int:profile_id>/edit', 'edit_profile', edit_profile, methods=['GET'])
app.add_url_rule('/api/profile', 'create_profile', create_profile, methods=['POST'])
app.add_url_rule('/api/profile/<int:profile_id>', 'update_profile', update_profile, methods=['POST', 'PUT'])
app.add_url_rule('/api/profile/<int:profile_id>', 'delete_profile', delete_profile, methods=['DELETE'])

# Users routes
app.add_url_rule('/users', 'users_page', users_page)
app.add_url_rule('/api/users', 'list_users', list_users)
app.add_url_rule('/user/new', 'new_user', new_user)
app.add_url_rule('/user/<int:user_id>/edit', 'edit_user', edit_user, methods=['GET'])
app.add_url_rule('/api/user', 'create_user', create_user, methods=['POST'])
app.add_url_rule('/api/user/<int:user_id>', 'update_user', update_user, methods=['POST', 'PUT'])
app.add_url_rule('/api/user/<int:user_id>', 'delete_user', delete_user, methods=['DELETE'])

# Quiz sharing routes
app.add_url_rule('/api/quiz/create-share-link', 'create_quiz_share_link', create_quiz_share_link, methods=['POST'])
app.add_url_rule('/share/<share_uuid>', 'show_share_page', show_share_page)
app.add_url_rule('/share/<share_uuid>/click', 'track_share_click', track_share_click)


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
    # Agrégats par thème large
    agg_broad_rows = (db.session.query(
                        Question.broad_theme_id,
                        BroadTheme.name,
                        func.coalesce(func.sum(UserQuestionStat.times_answered), 0),
                        func.coalesce(func.sum(UserQuestionStat.success_count), 0)
                      )
                      .join(Question, Question.id == UserQuestionStat.question_id)
                      .outerjoin(BroadTheme, BroadTheme.id == Question.broad_theme_id)
                      .filter(UserQuestionStat.user_id == g.current_user.id)
                      .group_by(Question.broad_theme_id, BroadTheme.name)
                      .order_by(func.coalesce(func.sum(UserQuestionStat.times_answered), 0).desc())
                      .all())
    agg_by_broad = [
        {
            'theme_id': row[0],
            'theme_name': row[1] or 'Sans thème',
            'answered': int(row[2] or 0),
            'success': int(row[3] or 0),
            'rate': (float(row[3]) / float(row[2]) * 100.0) if (row[2] or 0) > 0 else 0.0,
        }
        for row in agg_broad_rows
    ]
    # Agrégats par thème spécifique
    agg_spec_rows = (db.session.query(
                        Question.specific_theme_id,
                        SpecificTheme.name,
                        func.coalesce(func.sum(UserQuestionStat.times_answered), 0),
                        func.coalesce(func.sum(UserQuestionStat.success_count), 0)
                      )
                      .join(Question, Question.id == UserQuestionStat.question_id)
                      .outerjoin(SpecificTheme, SpecificTheme.id == Question.specific_theme_id)
                      .filter(UserQuestionStat.user_id == g.current_user.id)
                      .group_by(Question.specific_theme_id, SpecificTheme.name)
                      .order_by(func.coalesce(func.sum(UserQuestionStat.times_answered), 0).desc())
                      .all())
    agg_by_specific = [
        {
            'specific_theme_id': row[0],
            'specific_theme_name': row[1] or 'Sans sous-thème',
            'answered': int(row[2] or 0),
            'success': int(row[3] or 0),
            'rate': (float(row[3]) / float(row[2]) * 100.0) if (row[2] or 0) > 0 else 0.0,
        }
        for row in agg_spec_rows
    ]
    # Agrégats par difficulté
    agg_diff_rows = (db.session.query(
                        Question.difficulty_level,
                        func.coalesce(func.sum(UserQuestionStat.times_answered), 0),
                        func.coalesce(func.sum(UserQuestionStat.success_count), 0)
                      )
                      .join(Question, Question.id == UserQuestionStat.question_id)
                      .filter(UserQuestionStat.user_id == g.current_user.id)
                      .group_by(Question.difficulty_level)
                      .order_by(Question.difficulty_level)
                      .all())
    agg_by_difficulty = [
        {
            'difficulty': row[0],
            'answered': int(row[1] or 0),
            'success': int(row[2] or 0),
            'rate': (float(row[2]) / float(row[1]) * 100.0) if (row[1] or 0) > 0 else 0.0,
        }
        for row in agg_diff_rows
    ]
    # Compteurs de sessions
    sessions_completed = 0
    sessions_abandoned = 0
    if getattr(g, 'current_user', None):
        sessions_completed = (UserQuizSession.query
                              .filter_by(user_id=g.current_user.id, status='completed')
                              .count())
        sessions_abandoned = (UserQuizSession.query
                              .filter_by(user_id=g.current_user.id, status='abandoned')
                              .count())

    return render_template('me.html',
                           stats=stats,
                           total_answers=total_answers,
                           total_success=total_success,
                           agg_by_broad=agg_by_broad,
                           agg_by_specific=agg_by_specific,
                           agg_by_difficulty=agg_by_difficulty,
                           sessions_completed=sessions_completed,
                           sessions_abandoned=sessions_abandoned)


# ================== Questions sauvegardées ==================

@app.route('/api/questions/<int:question_id>/save', methods=['POST'])
def toggle_save_question(question_id: int):
    """Toggle (sauvegarder / désauvegarder) une question pour l'utilisateur connecté."""
    if not g.current_user:
        return {'success': False, 'error': 'Connexion requise'}, 401
    
    question = Question.query.get_or_404(question_id)
    
    # Vérifier si la question est déjà sauvegardée
    existing = SavedQuestion.query.filter_by(
        user_id=g.current_user.id,
        question_id=question_id
    ).first()
    
    if existing:
        # Désauvegarder
        db.session.delete(existing)
        db.session.commit()
        return {
            'success': True,
            'action': 'removed',
            'message': 'Question retirée des favoris'
        }
    else:
        # Sauvegarder
        saved_q = SavedQuestion(
            user_id=g.current_user.id,
            question_id=question_id
        )
        db.session.add(saved_q)
        db.session.commit()
        return {
            'success': True,
            'action': 'added',
            'message': 'Question ajoutée aux favoris'
        }


@app.route('/api/questions/<int:question_id>/is-saved')
def check_question_saved(question_id: int):
    """Vérifier si une question est sauvegardée par l'utilisateur connecté."""
    if not g.current_user:
        return {'is_saved': False}
    
    existing = SavedQuestion.query.filter_by(
        user_id=g.current_user.id,
        question_id=question_id
    ).first()
    
    return {'is_saved': existing is not None}


@app.route('/saved-questions')
def saved_questions_page():
    """Page de consultation des questions sauvegardées par l'utilisateur."""
    if not g.current_user:
        return redirect(url_for('play_quiz'))
    
    # Récupérer toutes les questions sauvegardées avec join pour optimisation
    saved_items = (SavedQuestion.query
                   .filter_by(user_id=g.current_user.id)
                   .join(Question)
                   .order_by(SavedQuestion.created_at.desc())
                   .all())
    
    return render_template('saved_questions.html', saved_items=saved_items)


@app.route('/preferences', methods=['GET', 'POST'])
def preferences():
    if not g.current_user:
        return redirect(url_for('play_quiz'))

    # Seuls les utilisateurs avec mot de passe peuvent accéder aux préférences
    if not g.current_user.password_hash:
        flash("Cette page n'est accessible qu'aux utilisateurs enregistrés.", "warning")
        return redirect(url_for('play_quiz'))

    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()

        # Validation basique de l'email
        if email and not re.match(r'^[^@]+@[^@]+\.[^@]+$', email):
            flash("Adresse email invalide.", "danger")
            return render_template('preferences.html', user=g.current_user)

        # Mettre à jour l'email
        g.current_user.email = email

        # Traiter les préférences de jeu et de notification
        prefs = g.current_user.get_preferences()
        prefs['double_click_validation'] = (request.form.get('double_click_validation') == '1')
        prefs['notify_email_on_message'] = (request.form.get('notify_email_on_message') == '1')
        g.current_user.set_preferences(prefs)

        db.session.commit()
        flash("Préférences mises à jour avec succès.", "success")
        return redirect(url_for('preferences'))

    return render_template('preferences.html', user=g.current_user)


@app.route('/delete-account', methods=['POST'])
def delete_account():
    """Supprime définitivement le compte utilisateur et toutes ses données."""
    if not g.current_user:
        return redirect(url_for('play_quiz'))

    # Seuls les utilisateurs avec mot de passe peuvent supprimer leur compte
    if not g.current_user.password_hash:
        flash("Cette action n'est disponible que pour les utilisateurs enregistrés.", "warning")
        return redirect(url_for('preferences'))

    user_id = g.current_user.id
    username = g.current_user.username

    try:
        # Supprimer explicitement les données liées pour s'assurer qu'elles sont supprimées
        UserQuestionStat.query.filter_by(user_id=user_id).delete()
        UserQuizSession.query.filter_by(user_id=user_id).delete()

        # Supprimer l'utilisateur (les foreign keys avec cascade s'occuperont du reste)
        db.session.delete(g.current_user)
        db.session.commit()

        # Nettoyer la session
        session.clear()

        flash(f"Le compte de {username} a été supprimé définitivement.", "success")
        return redirect(url_for('index'))

    except Exception as e:
        db.session.rollback()
        flash("Une erreur est survenue lors de la suppression du compte. Veuillez réessayer.", "danger")
        return redirect(url_for('preferences'))


# ================== Fichiers uploadés (serveur) ==================

@app.route('/uploads/<path:filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


# ================== Fichiers sons ==================
@app.route('/sounds/<path:filename>')
def sounds_file(filename):
    # Sert les fichiers audio depuis ressources/sounds
    return send_from_directory(app.config['SOUNDS_FOLDER'], filename)


@app.route('/')
def index():
    """Accueil: page publique si non connecté, sinon page de jeu."""
    if getattr(g, 'current_user', None):
        return redirect(url_for('play_quiz'))
    return render_template('home_public.html')


@app.route('/a-propos')
def about_page():
    """Page publique présentant les intentions et la vision de CacheQuiz."""
    return render_template('about.html')


@app.route('/contact', methods=['GET', 'POST'])
def contact_page():
    print(f"[CONTACT] Method: {request.method}")
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip()
        message = (request.form.get('message') or '').strip()
        print(f"[CONTACT] Received: name='{name}', email='{email}', message='{message[:50]}...'")

        if not name or not email or not message:
            print(f"[CONTACT] Validation failed: name={bool(name)}, email={bool(email)}, message={bool(message)}")
            flash('Tous les champs sont requis.', 'danger')
            return render_template('contact.html')

        try:
            print("[CONTACT] Creating ContactMessage...")
            # Créer le message de contact
            contact_msg = ContactMessage(
                visitor_name=name,
                visitor_email=email,
                message=message
            )
            db.session.add(contact_msg)
            db.session.flush()
            print(f"[CONTACT] ContactMessage created with id={contact_msg.id}")

            # Trouver les administrateurs (utilisateurs avec profil "Administrateur")
            print("[CONTACT] Looking for admin profile...")
            admin_profile = Profile.query.filter_by(name='Administrateur').first()
            admin_users = []
            if admin_profile:
                print(f"[CONTACT] Found admin profile id={admin_profile.id}")
                admin_users = User.query.filter_by(profile_id=admin_profile.id, is_active=True).all()
                print(f"[CONTACT] Found {len(admin_users)} active admin users: {[u.username for u in admin_users]}")
            else:
                print("[CONTACT] No admin profile found!")

            # Créer une conversation si il y a des admins
            if admin_users:
                print("[CONTACT] Creating conversation...")
                subject = f"Contact: Message de {name}"
                conv = Conversation(subject=subject, context_type='contact_message', context_id=contact_msg.id)
                db.session.add(conv)
                db.session.flush()
                print(f"[CONTACT] Conversation created with id={conv.id}")

                # Ajouter les participants (admins)
                for admin in admin_users:
                    print(f"[CONTACT] Adding participant: {admin.username} (id={admin.id})")
                    db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=admin.id, last_read_at=None))

                # Message initial
                content = f"Message de contact de {name} ({email}):\n\n{message}"
                print("[CONTACT] Creating initial message...")
                msg = ConversationMessage(conversation_id=conv.id, sender_id=None, content=content)  # sender_id=None pour les messages système
                db.session.add(msg)

                # Lier la conversation au message de contact
                contact_msg.conversation_id = conv.id

                # Envoyer emails aux admins ayant activé les notifications
                for admin in admin_users:
                    prefs = admin.get_preferences()
                    notify = prefs.get('notify_email_on_message', False)
                    has_email = bool(admin.email)
                    print(f"[CONTACT] Admin {admin.username}: notify={notify}, has_email={has_email}")
                    if notify and has_email:
                        try:
                            send_email_optional(
                                to_email=admin.email,
                                subject=f"Nouveau message de contact: {subject}",
                                body=f"Un nouveau message de contact a été reçu de {name}.\n\n{message}\n\nAccéder à la conversation: {request.host_url.rstrip('/')}/messages"
                            )
                            print(f"[CONTACT] Email sent to {admin.email}")
                        except Exception as e:
                            print(f"[CONTACT] Email error for {admin.email}: {e}")

            print("[CONTACT] Committing transaction...")
            db.session.commit()
            print("[CONTACT] Transaction committed successfully")
            flash('Merci, votre message a été envoyé.', 'success')
            return redirect(url_for('contact_page'))

        except Exception as e:
            db.session.rollback()
            print(f"[CONTACT] Error during contact message creation: {e}")
            import traceback
            traceback.print_exc()
            flash('Une erreur est survenue lors de l\'envoi de votre message.', 'danger')
            return render_template('contact.html')

    return render_template('contact.html')


# ================== Signalement de problème sur une question ==================

@app.route('/api/report/form')
def report_form():
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return "<div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-warning'>Vous devez être connecté avec un compte protégé par mot de passe pour signaler un problème.</div></div>", 200

    qid = (request.args.get('question_id') or '').strip()
    if not qid.isdigit():
        return "<div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Identifiant de question invalide.</div></div>", 200

    question = Question.query.get(int(qid))
    if not question:
        return "<div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Question introuvable.</div></div>", 200

    rule_set_slug = (request.args.get('rule_set') or '').strip()
    rule_set = None
    if rule_set_slug:
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

    author_user = question.author_user
    rule_creator = rule_set.created_by_user if rule_set else None

    inner = render_template('report_form.html', question=question, rule_set=rule_set, author_user=author_user, rule_creator=rule_creator)
    # Remplacer entièrement le conteneur pour l'afficher
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"


@app.route('/api/report/submit', methods=['POST'])
def report_submit():
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return "<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-warning'>Vous devez être connecté avec un compte protégé par mot de passe.</div></div></div>", 200

    qid = (request.form.get('question_id') or '').strip()
    reason = (request.form.get('reason') or '').strip()
    details = (request.form.get('details') or '').strip()
    rule_set_slug = (request.form.get('rule_set') or '').strip()

    if not qid.isdigit():
        return "<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Identifiant de question invalide.</div></div></div>", 200
    if not reason or not details:
        return "<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Merci de préciser la raison et les détails.</div></div></div>", 200

    question = Question.query.get(int(qid))
    if not question:
        return "<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Question introuvable.</div></div></div>", 200

    rule_set = None
    if rule_set_slug:
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

    # Déterminer les destinataires
    to_author = (request.form.get('to_author') == '1')
    to_rule_creator = (request.form.get('to_rule_creator') == '1')
    to_admins = (request.form.get('to_admins') == '1')

    recipient_ids = set()
    if to_author and question.author_id:
        recipient_ids.add(int(question.author_id))
    if to_rule_creator and rule_set and rule_set.created_by_user_id:
        recipient_ids.add(int(rule_set.created_by_user_id))
    if to_admins:
        for adm in User.query.filter_by(is_admin=True, is_active=True).all():
            recipient_ids.add(adm.id)

    # Exclure l'expéditeur
    if user.id in recipient_ids:
        recipient_ids.remove(user.id)

    try:
        # Créer la conversation
        subject = f"Signalement Q{question.id}: {question.question_text[:60]}"
        conv = Conversation(subject=subject, context_type='question_report', context_id=None)
        db.session.add(conv)
        db.session.flush()

        # Participants: reporter + destinataires
        db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=user.id, last_read_at=datetime.utcnow()))
        for rid in recipient_ids:
            db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=rid, last_read_at=None))

        # Message initial
        content = f"Raison: {reason}\n\n{details}"
        msg = ConversationMessage(conversation_id=conv.id, sender_id=user.id, content=content)
        db.session.add(msg)
        db.session.flush()

        # Créer le report et relier la conversation
        report = QuestionReport(
            question_id=question.id,
            rule_set_id=(rule_set.id if rule_set else None),
            reporter_id=user.id,
            reason=reason,
            details=details,
            status='open',
            conversation_id=conv.id,
        )
        db.session.add(report)
        conv.context_id = report.id

        db.session.commit()

        # Envoi emails (optionnel)
        # Récupérer préférences des destinataires
        if recipient_ids:
            recips = User.query.filter(User.id.in_(list(recipient_ids))).all()
            for r in recips:
                prefs = r.get_preferences()
                if prefs.get('notify_email_on_message') and r.email:
                    try:
                        send_email_optional(
                            to_email=r.email,
                            subject=f"Nouveau message: {subject}",
                            body=f"Un nouveau signalement a été créé par {user.username}.\n\n{details}\n\nAccéder à la conversation: {request.host_url.rstrip('/')}/messages"
                        )
                    except Exception:
                        pass

        html = (
            "<div id='modal-root' class='modal-overlay' style='display:flex'>"
            "<div class='modal-content' style='padding:1.5rem'>"
            "<h3>Merci pour votre signalement</h3>"
            "<p>Votre message a été envoyé aux destinataires sélectionnés.</p>"
            "<div style='display:flex; gap:.5rem; justify-content:flex-end'>"
            "<a class='btn btn-primary' href='/messages'>Ouvrir la messagerie</a>"
            "<button class='btn btn-secondary' onclick=\"document.getElementById('modal-root').style.display='none'\">Fermer</button>"
            "</div>"
            "</div>"
            "</div>"
        )
        return html
    except Exception as e:
        db.session.rollback()
        return f"<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Erreur lors de l'envoi: {str(e)}</div></div></div>", 200


# ================== Messagerie ==================

@app.route('/messages')
def messages_home():
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return redirect(url_for('play_quiz'))
    return render_template('messages.html')


@app.route('/api/messages/list')
def api_messages_list():
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return "<div class='alert alert-warning'>Connectez-vous pour voir vos messages.</div>", 200

    parts = ConversationParticipant.query.filter_by(user_id=user.id).all()
    # Récupérer conversations et derniers messages
    items = []
    for p in parts:
        conv = Conversation.query.get(p.conversation_id)
        if not conv:
            continue
        last_msg = ConversationMessage.query.filter_by(conversation_id=conv.id).order_by(ConversationMessage.created_at.desc()).first()

        # Calcul des messages non lus (même logique que le widget)
        if p.last_read_at is None:
            # Pour les nouveaux participants, compter tous les messages sauf ceux de l'utilisateur
            unread_count = ConversationMessage.query.filter(
                ConversationMessage.conversation_id == p.conversation_id,
                or_(ConversationMessage.sender_id.is_(None), ConversationMessage.sender_id != user.id)
            ).count()
        else:
            # Pour les participants existants, compter les messages après last_read_at
            unread_count = ConversationMessage.query.filter(
                ConversationMessage.conversation_id == p.conversation_id,
                ConversationMessage.created_at > p.last_read_at,
                or_(ConversationMessage.sender_id.is_(None), ConversationMessage.sender_id != user.id)
            ).count()

        items.append((conv, last_msg, unread_count))

    # Trier par date du dernier message descendant (plus récent en premier)
    items.sort(key=lambda x: x[1].created_at if x[1] else datetime.min, reverse=True)

    return render_template('partials/messages_list.html', items=items)


@app.route('/api/messages/thread/<int:conv_id>')
def api_messages_thread(conv_id: int):
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return "<div class='alert alert-warning'>Connectez-vous pour voir cette conversation.</div>", 200

    part = ConversationParticipant.query.filter_by(conversation_id=conv_id, user_id=user.id).first()
    if not part:
        return "<div class='alert alert-danger'>Accès refusé.</div>", 200

    conv = Conversation.query.get(conv_id)
    if not conv:
        return "<div class='alert alert-danger'>Conversation introuvable.</div>", 200

    print(f"[THREAD] Loading thread {conv_id} for user {user.username}, last_read_at was: {part.last_read_at}")

    # Marquer comme lu
    try:
        old_last_read = part.last_read_at
        part.last_read_at = datetime.utcnow()
        db.session.commit()
        print(f"[THREAD] Updated last_read_at from {old_last_read} to {part.last_read_at}")
    except Exception as e:
        db.session.rollback()
        print(f"[THREAD] Error updating last_read_at: {e}")

    messages = ConversationMessage.query.filter_by(conversation_id=conv.id).order_by(ConversationMessage.created_at.asc()).all()
    return render_template('partials/conversation_thread.html', conversation=conv, messages=messages, me=user)


@app.route('/api/messages/mark-unread/<int:conv_id>', methods=['POST'])
def api_messages_mark_unread(conv_id: int):
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return "Unauthorized", 403

    part = ConversationParticipant.query.filter_by(conversation_id=conv_id, user_id=user.id).first()
    if not part:
        return "Access denied", 403

    try:
        print(f"[MARK_UNREAD] User {user.username} marking conversation {conv_id} as unread")
        part.last_read_at = None  # Remettre à None pour marquer comme non lu
        db.session.commit()
        print(f"[MARK_UNREAD] Successfully marked conversation {conv_id} as unread for user {user.username}")
        return "", 200  # HTMX ne fait rien avec le contenu, juste le statut
    except Exception as e:
        db.session.rollback()
        print(f"[MARK_UNREAD] Error marking as unread: {e}")
        return "Error", 500


@app.route('/api/messages/delete/<int:conv_id>', methods=['POST'])
def api_messages_delete(conv_id: int):
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return redirect(url_for('play_quiz'))

    part = ConversationParticipant.query.filter_by(conversation_id=conv_id, user_id=user.id).first()
    if not part:
        # Retourner directement le HTML de la page avec un message d'erreur
        flash("Accès refusé à cette conversation.", "danger")
        return render_template('messages_content.html')

    try:
        print(f"[DELETE_CONV] User {user.username} deleting conversation {conv_id}")

        # Supprimer la participation de l'utilisateur
        db.session.delete(part)

        # Vérifier s'il reste des participants
        remaining_parts = ConversationParticipant.query.filter_by(conversation_id=conv_id).count()

        if remaining_parts == 0:
            # Plus de participants, supprimer complètement la conversation et ses messages
            print(f"[DELETE_CONV] No more participants, deleting conversation {conv_id} completely")

            # Supprimer les messages
            ConversationMessage.query.filter_by(conversation_id=conv_id).delete()

            # Supprimer les rapports/questions liés si c'est un signalement
            conv = Conversation.query.get(conv_id)
            if conv and conv.context_type == 'question_report' and conv.context_id:
                QuestionReport.query.filter_by(id=conv.context_id).delete()
            elif conv and conv.context_type == 'contact_message' and conv.context_id:
                ContactMessage.query.filter_by(id=conv.context_id).delete()

            # Supprimer la conversation
            db.session.delete(conv)
        else:
            print(f"[DELETE_CONV] {remaining_parts} participants remaining, keeping conversation {conv_id}")

        db.session.commit()
        print(f"[DELETE_CONV] Successfully deleted conversation {conv_id} for user {user.username}")

        # Retourner directement le HTML de la page messages rechargée avec un message de succès
        flash("Conversation supprimée de votre boîte de réception.", "success")
        return render_template('messages_content.html')

    except Exception as e:
        db.session.rollback()
        print(f"[DELETE_CONV] Error deleting conversation: {e}")
        flash("Erreur lors de la suppression de la conversation.", "danger")
        return render_template('messages_content.html')


@app.route('/api/messages/send', methods=['POST'])
def api_messages_send():
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return "<div class='alert alert-warning'>Connectez-vous pour envoyer un message.</div>", 200

    conv_id_raw = (request.form.get('conversation_id') or '').strip()
    content = (request.form.get('content') or '').strip()
    if not conv_id_raw.isdigit() or not content:
        return "<div class='alert alert-danger'>Données invalides.</div>", 200

    conv_id = int(conv_id_raw)
    part = ConversationParticipant.query.filter_by(conversation_id=conv_id, user_id=user.id).first()
    if not part:
        return "<div class='alert alert-danger'>Accès refusé.</div>", 200

    try:
        msg = ConversationMessage(conversation_id=conv_id, sender_id=user.id, content=content)
        db.session.add(msg)
        db.session.commit()

        # Notifier les autres participants
        other_parts = ConversationParticipant.query.filter(ConversationParticipant.conversation_id == conv_id, ConversationParticipant.user_id != user.id).all()
        if other_parts:
            recipients = User.query.filter(User.id.in_([p.user_id for p in other_parts])).all()
            conv = Conversation.query.get(conv_id)
            for r in recipients:
                prefs = r.get_preferences()
                if prefs.get('notify_email_on_message') and r.email:
                    try:
                        send_email_optional(
                            to_email=r.email,
                            subject=f"Nouveau message: {conv.subject or 'Conversation'}",
                            body=f"{user.username} a envoyé un nouveau message.\n\n{content}\n\nAccéder à la conversation: {request.host_url.rstrip('/')}/messages"
                        )
                    except Exception:
                        pass

        # Réafficher le fil
        messages = ConversationMessage.query.filter_by(conversation_id=conv_id).order_by(ConversationMessage.created_at.asc()).all()
        conv = Conversation.query.get(conv_id)
        return render_template('partials/conversation_thread.html', conversation=conv, messages=messages, me=user)
    except Exception as e:
        db.session.rollback()
        return f"<div class='alert alert-danger'>Erreur lors de l'envoi: {str(e)}</div>", 200


@app.route('/admin')
def admin_page():
    """Page d'administration avec la liste des questions"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    # Calcul des statistiques
    total_questions = Question.query.count()
    online_questions = Question.query.filter_by(is_published=True).count()

    return render_template('index.html', 
                           total_questions=total_questions, 
                           online_questions=online_questions)


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
    
    filtered_count = len(questions)
    total_count = Question.query.count()
    
    return render_template('questions_list.html', questions=questions, view=view, sort_by=sort_by, sort_order=sort_order, filtered_count=filtered_count, total_count=total_count)

# Question routes
app.add_url_rule('/questions', 'list_questions', list_questions)
















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
    Retourne (playlist_key, index_key, score_key, correct_key, breakdown_key, streak_key, perfect_key, user_id_str)
    """
    user_id_str = str(g.current_user.id) if getattr(g, 'current_user', None) else 'anon'
    prefix = f"{user_id_str}:{rule_set_slug}"
    playlist_key = f"quiz_playlist:{prefix}"
    index_key = f"quiz_playlist_index:{prefix}"
    score_key = f"quiz_score:{prefix}"
    correct_key = f"quiz_correct_answers:{prefix}"
    breakdown_key = f"quiz_score_breakdown:{prefix}"
    streak_key = f"quiz_combo_streak:{prefix}"
    perfect_key = f"quiz_perfect_awarded:{prefix}"
    return playlist_key, index_key, score_key, correct_key, breakdown_key, streak_key, perfect_key, user_id_str


def _append_score_breakdown(breakdown_key: str, event: dict):
    """Ajoute un événement de score dans la liste stockée en session."""
    try:
        history = session.get(breakdown_key)
        if not isinstance(history, list):
            history = []
        history.append(event)
        session[breakdown_key] = history
    except Exception as exc:
        print(f"[QUIZ SCORE] Impossible d'ajouter le breakdown: {exc}")


def _get_user_answered_keywords(user_id: int) -> set[int]:
    """Récupère les IDs de tous les keywords déjà répondus par l'utilisateur."""
    if not user_id:
        return set()
    
    try:
        # Récupérer toutes les questions déjà répondues
        answered_question_ids = {row.question_id for row in 
                                 UserQuestionStat.query.with_entities(UserQuestionStat.question_id)
                                 .filter_by(user_id=user_id).all()}
        
        if not answered_question_ids:
            return set()
        
        # Récupérer les keywords de ces questions
        from sqlalchemy import select
        keyword_ids = set()
        result = db.session.execute(
            select(db.literal_column('keyword_id'))
            .select_from(db.text('question_keywords'))
            .where(db.literal_column('question_id').in_(answered_question_ids))
        )
        keyword_ids = {row[0] for row in result}
        return keyword_ids
    except Exception as e:
        print(f"[KEYWORDS] Erreur lors de la récupération des keywords répondus: {e}")
        return set()


def _select_questions_with_keyword_logic(
    candidate_ids: list[int],
    seen_question_ids: set[int],
    used_keywords: set[int],
    answered_keywords: set[int],
    prevent_duplicate_keywords: bool,
    quota: int
) -> tuple[list[int], set[int], dict[str, any]]:
    """
    Sélectionne les questions en respectant la logique des keywords.
    
    Priorités (par ordre d'importance):
    1. Condition QuizRuleSet (ABSOLU) - déjà appliqué dans candidate_ids
    2. Pas de doublons de keywords dans le quiz (si prevent_duplicate_keywords)
    3. Pas de questions déjà répondues
    4. Pas de keywords déjà répondus
    
    Retourne: (selected_ids, used_keywords_updated, stats)
    """
    if not candidate_ids or quota <= 0:
        return [], used_keywords, {'perfect': True, 'conditions_met': []}
    
    # Charger toutes les questions candidates avec leurs keywords
    candidates = Question.query.filter(Question.id.in_(candidate_ids)).options(
        db.joinedload(Question.keywords)
    ).all()
    
    # Stats pour le debug
    stats = {
        'perfect': True,
        'total_candidates': len(candidates),
        'conditions_met': [],
        'fallback_used': []
    }
    
    selected_ids = []
    current_used_keywords = set(used_keywords)
    
    # Fonction pour scorer une question selon les priorités
    def score_question(q: Question) -> tuple:
        """Retourne un tuple de score (plus élevé = meilleur). Format: (prio1, prio2, prio3, prio4)"""
        q_keywords = {kw.id for kw in q.keywords}
        
        # Priorité 1: Pas de doublons de keywords (si activé)
        if prevent_duplicate_keywords and q_keywords:
            has_duplicate_keyword = bool(q_keywords & current_used_keywords)
        else:
            has_duplicate_keyword = False
        
        # Priorité 2: Question non répondue
        is_unseen = q.id not in seen_question_ids
        
        # Priorité 3: Keywords non répondus
        if q_keywords and answered_keywords:
            has_unanswered_keywords = bool(q_keywords & answered_keywords)
        else:
            has_unanswered_keywords = False
        
        # Questions sans keywords ont un bonus (pas de risque de doublon)
        no_keywords = len(q_keywords) == 0
        
        # Retourner score (format: pas de doublon keyword, non vue, pas keyword répondu, sans keyword)
        return (
            not has_duplicate_keyword,  # Vrai = 1, Faux = 0 (on veut True en premier)
            is_unseen,
            not has_unanswered_keywords,
            no_keywords
        )
    
    # Trier les candidats par score (du meilleur au pire)
    sorted_candidates = sorted(candidates, key=score_question, reverse=True)
    
    # Sélectionner jusqu'au quota
    for q in sorted_candidates:
        if len(selected_ids) >= quota:
            break
        
        q_keywords = {kw.id for kw in q.keywords}
        
        # Vérifier si on respecte toutes les conditions
        conditions_perfect = True
        
        # Condition 2: Pas de doublons de keywords
        if prevent_duplicate_keywords and q_keywords and (q_keywords & current_used_keywords):
            conditions_perfect = False
            stats['fallback_used'].append('keyword_duplicate')
        
        # Condition 3: Question non répondue
        if q.id in seen_question_ids:
            conditions_perfect = False
            stats['fallback_used'].append('question_already_seen')
        
        # Condition 4: Keywords non répondus
        if q_keywords and answered_keywords and (q_keywords & answered_keywords):
            conditions_perfect = False
            stats['fallback_used'].append('keyword_already_answered')
        
        if not conditions_perfect:
            stats['perfect'] = False
        
        selected_ids.append(q.id)
        current_used_keywords.update(q_keywords)
    
    # Statistiques finales
    if stats['perfect']:
        stats['conditions_met'] = ['Toutes les conditions respectées ✅']
    else:
        fallback_counts = {}
        for fb in stats['fallback_used']:
            fallback_counts[fb] = fallback_counts.get(fb, 0) + 1
        stats['conditions_met'] = [
            f"⚠️ {count}x {reason.replace('_', ' ')}" 
            for reason, count in fallback_counts.items()
        ]
    
    return selected_ids, current_used_keywords, stats


def _generate_quiz_playlist(rule_set: QuizRuleSet, current_user_id: int | None) -> list[int]:
    """
    Génère la playlist (liste d'IDs de questions) pour un quiz à longueur fixe.
    
    Priorités de sélection:
    1. Respecter les conditions du QuizRuleSet (ABSOLU)
    2. Éviter les doublons de keywords dans le quiz
    3. Éviter les questions déjà répondues
    4. Éviter les keywords déjà répondus
    
    En mode 'manual': réordonne la liste sélectionnée en appliquant la logique keywords.
    En mode 'auto': respecte les quotas par difficulté avec gestion keywords.
    """
    try:
        print(f"\n[QUIZ PLAYLIST] === Génération playlist pour {rule_set.name} ===")
        
        # Récupérer les IDs déjà vus par l'utilisateur (si connecté)
        seen_ids = set()
        answered_keywords = set()
        if current_user_id:
            seen_ids = {row.question_id for row in 
                       UserQuestionStat.query.with_entities(UserQuestionStat.question_id)
                       .filter_by(user_id=current_user_id).all()}
            answered_keywords = _get_user_answered_keywords(current_user_id)
            print(f"[QUIZ PLAYLIST] Utilisateur {current_user_id}: {len(seen_ids)} questions vues, {len(answered_keywords)} keywords répondus")
        
        prevent_duplicate_keywords = rule_set.prevent_duplicate_keywords
        print(f"[QUIZ PLAYLIST] Prévention doublons keywords: {'OUI' if prevent_duplicate_keywords else 'NON'}")

        # Mode manuel: partir de la sélection explicite
        if rule_set.question_selection_mode == 'manual' and rule_set.selected_questions:
            print(f"[QUIZ PLAYLIST] Mode MANUEL: {len(rule_set.selected_questions)} questions sélectionnées")
            selected = [q for q in rule_set.selected_questions if q.is_published]
            candidate_ids = [q.id for q in selected]
            
            # Appliquer la logique keywords sur toute la sélection
            playlist, _, stats = _select_questions_with_keyword_logic(
                candidate_ids=candidate_ids,
                seen_question_ids=seen_ids,
                used_keywords=set(),
                answered_keywords=answered_keywords,
                prevent_duplicate_keywords=prevent_duplicate_keywords,
                quota=len(candidate_ids)
            )
            
            # Logs
            if stats['perfect']:
                print(f"[QUIZ PLAYLIST] ✅ CONDITIONS PARFAITES: {', '.join(stats['conditions_met'])}")
            else:
                print(f"[QUIZ PLAYLIST] ⚠️ COMPROMIS NÉCESSAIRES:")
                for condition in stats['conditions_met']:
                    print(f"[QUIZ PLAYLIST]    {condition}")
            
            print(f"[QUIZ PLAYLIST] Playlist générée: {len(playlist)} questions")
            return playlist

        # Mode auto: quotas par difficulté et filtres de thèmes
        qmap = rule_set.get_questions_per_difficulty() or {}
        allowed_diffs = rule_set.get_allowed_difficulties() or [1, 2, 3, 4, 5]
        print(f"[QUIZ PLAYLIST] Mode AUTO: difficultés {allowed_diffs}, quotas {qmap}")
        order_mode = getattr(rule_set, 'question_order_mode', 'difficulty_ascending') or 'difficulty_ascending'
        if order_mode not in ['difficulty_ascending', 'full_shuffle']:
            order_mode = 'difficulty_ascending'
        print(f"[QUIZ PLAYLIST] Ordre des questions: {order_mode}")

        # Construire la requête de base selon le set de règles
        base_params = {'rule_set': rule_set.slug}
        base_query = _apply_quiz_filters(Question.query.filter(Question.is_published.is_(True)), base_params)

        # Préparer par difficulté avec logique keywords
        per_diff_ids: dict[int, list[int]] = {}
        used_keywords_global = set()
        all_stats = []
        
        for d in allowed_diffs:
            quota = int(qmap.get(str(d), 0) or 0)
            if quota <= 0:
                per_diff_ids[d] = []
                continue

            print(f"[QUIZ PLAYLIST] Difficulté {d}: quota={quota}")
            
            q_for_diff = base_query.filter(Question.difficulty_level == d)
            candidates = q_for_diff.with_entities(Question.id).all()
            candidate_ids = [row.id for row in candidates]
            
            print(f"[QUIZ PLAYLIST]   Candidats disponibles: {len(candidate_ids)}")
            
            # Appliquer la logique keywords
            chosen, used_keywords_global, stats = _select_questions_with_keyword_logic(
                candidate_ids=candidate_ids,
                seen_question_ids=seen_ids,
                used_keywords=used_keywords_global,
                answered_keywords=answered_keywords,
                prevent_duplicate_keywords=prevent_duplicate_keywords,
                quota=quota
            )
            
            per_diff_ids[d] = chosen
            all_stats.append({
                'difficulty': d,
                'quota': quota,
                'selected': len(chosen),
                'perfect': stats['perfect'],
                'conditions': stats['conditions_met']
            })
            
            print(f"[QUIZ PLAYLIST]   Sélectionnés: {len(chosen)}/{quota}")
            if not stats['perfect']:
                for condition in stats['conditions_met']:
                    print(f"[QUIZ PLAYLIST]     {condition}")

        # Construire la playlist selon le mode d'ordre choisi
        if order_mode == 'full_shuffle':
            playlist = []
            for diff in per_diff_ids:
                playlist.extend(per_diff_ids[diff])
            random.shuffle(playlist)
        else:
            playlist = []
            for diff in sorted(per_diff_ids.keys()):
                bucket = list(per_diff_ids.get(diff) or [])
                if len(bucket) > 1:
                    random.shuffle(bucket)
                playlist.extend(bucket)

        expected_total = sum(int(qmap.get(str(d), 0) or 0) for d in allowed_diffs)
        
        # Logs finaux
        print(f"\n[QUIZ PLAYLIST] === RÉSUMÉ FINAL ===")
        print(f"[QUIZ PLAYLIST] Playlist générée: {len(playlist)}/{expected_total} questions")
        
        # Vérifier si toutes les conditions sont parfaites
        all_perfect = all(stat['perfect'] for stat in all_stats)
        if all_perfect:
            print(f"[QUIZ PLAYLIST] ✅ CONDITIONS PARFAITES pour toutes les questions !")
        else:
            print(f"[QUIZ PLAYLIST] ⚠️ COMPROMIS NÉCESSAIRES:")
            for stat in all_stats:
                if not stat['perfect']:
                    print(f"[QUIZ PLAYLIST]   Difficulté {stat['difficulty']}: {', '.join(stat['conditions'])}")
        
        if len(playlist) < expected_total:
            print(f"[QUIZ PLAYLIST] ⚠️ Playlist incomplète. Pool insuffisant pour certains quotas.")
        
        print(f"[QUIZ PLAYLIST] Keywords uniques utilisés: {len(used_keywords_global)}")
        print(f"[QUIZ PLAYLIST] ==================\n")

        return playlist
    except Exception as e:
        print(f"[QUIZ PLAYLIST] ❌ ERREUR génération playlist: {e}")
        import traceback
        traceback.print_exc()
        return []


def _get_user_double_click_preference() -> bool:
    try:
        if getattr(g, 'current_user', None):
            prefs = g.current_user.get_preferences()
            if 'double_click_validation' in prefs:
                return bool(prefs.get('double_click_validation'))
    except Exception:
        pass
    return True


@app.route('/play')
def play_quiz():
    """Page pour choisir un set de règles et jouer au quiz."""
    rule_set = None
    rule_set_slug = request.args.get('rule_set', '').strip()
    auto_start_param = (request.args.get('auto_start') or '').strip().lower()
    auto_start = auto_start_param in ('1', 'true', 'yes', 'on')
    if rule_set_slug:
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
    else:
        # Si on arrive sans set explicite et qu'il existait une session en cours, l'abandonner
        if getattr(g, 'current_user', None):
            try:
                in_prog = UserQuizSession.query.filter_by(user_id=g.current_user.id, status='in_progress').all()
                for s in in_prog:
                    print(f"[QUIZ SESSION] Abandon session {s.id} while entering /play without specific rule_set (user={s.user_id})")
                    s.status = 'abandoned'
                    s.updated_at = datetime.utcnow()
                if in_prog:
                    db.session.commit()
            except Exception:
                db.session.rollback()

    # Récupérer tous les sets de règles actifs
    rule_sets = QuizRuleSet.query.filter_by(is_active=True).order_by(QuizRuleSet.name).all()

    quick_double_click_pref = _get_user_double_click_preference()
    if 'quick_double_click_enabled' in session:
        quick_double_click_enabled = bool(session.get('quick_double_click_enabled'))
    else:
        quick_double_click_enabled = quick_double_click_pref
        session['quick_double_click_enabled'] = quick_double_click_enabled

    return render_template('play.html',
                           rule_sets=rule_sets,
                           rule_set=rule_set,
                           quick_double_click=quick_double_click_enabled,
                           auto_start=auto_start)


@app.route('/play/<slug>')
def play_quiz_by_slug(slug):
    """
    Page pour jouer à un quiz spécifique via son slug.
    Route propre pour partage sur réseaux sociaux: /play/<slug>
    """
    rule_set = QuizRuleSet.query.filter_by(slug=slug, is_active=True).first()
    
    if not rule_set:
        # Redirection vers la page de sélection si le slug n'existe pas
        return redirect(url_for('play_quiz'))
    
    # Récupérer tous les sets de règles actifs pour le sélecteur
    rule_sets = QuizRuleSet.query.filter_by(is_active=True).order_by(QuizRuleSet.name).all()
    
    quick_double_click_pref = _get_user_double_click_preference()
    if 'quick_double_click_enabled' in session:
        quick_double_click_enabled = bool(session.get('quick_double_click_enabled'))
    else:
        quick_double_click_enabled = quick_double_click_pref
        session['quick_double_click_enabled'] = quick_double_click_enabled
    
    # Auto-démarrage activé par défaut pour cette route
    auto_start = True
    
    return render_template('play.html',
                           rule_sets=rule_sets,
                           rule_set=rule_set,
                           quick_double_click=quick_double_click_enabled,
                           auto_start=auto_start)


@app.route('/api/quiz/next')
def next_quiz_question():
    """Retourne la prochaine question du quiz en consommant une playlist pré-générée.
    Si aucune playlist n'existe encore pour ce set, la génère et la stocke en session.
    """
    try:
        params = request.args
        rule_set_slug = (params.get('rule_set') or '').strip()
        history_raw = (params.get('history') or '').strip()
        quick_double_click_param = params.get('quick_double_click')
        if quick_double_click_param is not None:
            quick_double_click = quick_double_click_param.lower() == 'true'
            session['quick_double_click_enabled'] = quick_double_click
        elif 'quick_double_click_enabled' in session:
            quick_double_click = bool(session.get('quick_double_click_enabled'))
        else:
            quick_double_click = _get_user_double_click_preference()
            session['quick_double_click_enabled'] = quick_double_click
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
        playlist_session_key = playlist_index_key = score_session_key = correct_answers_session_key = breakdown_session_key = streak_session_key = perfect_session_key = user_ns = None
        if rule_set:
            (
                playlist_session_key,
                playlist_index_key,
                score_session_key,
                correct_answers_session_key,
                breakdown_session_key,
                streak_session_key,
                perfect_session_key,
                user_ns,
            ) = _quiz_session_keys(rule_set.slug)

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
                if breakdown_session_key:
                    session[breakdown_session_key] = []
                if streak_session_key:
                    session[streak_session_key] = 0
                if perfect_session_key:
                    session[perfect_session_key] = False
                print(f"[QUIZ PLAYLIST] Générée (reset={not bool(history_raw)}) pour user={user_ns} set='{rule_set.slug}' (len={len(playlist)}): {playlist}")

                # Démarrer une UserQuizSession si utilisateur connecté
                if getattr(g, 'current_user', None):
                    try:
                        # Clore toute session précédente en cours pour ce set
                        prev = (UserQuizSession.query
                                .filter_by(user_id=g.current_user.id, rule_set_id=rule_set.id, status='in_progress')
                                .all())
                        for s in prev:
                            print(f"[QUIZ SESSION] Abandon in-progress session {s.id} for rule_set {s.rule_set_id} before starting new session (user={s.user_id})")
                            s.status = 'abandoned'
                            s.updated_at = datetime.utcnow()
                        # Créer une nouvelle session
                        new_session = UserQuizSession(
                            user_id=g.current_user.id,
                            rule_set_id=rule_set.id,
                            status='in_progress',
                            total_questions=len(playlist),
                            answered_count=0,
                            correct_count=0,
                            total_score=0
                        )
                        db.session.add(new_session)
                        db.session.commit()
                        print(f"[QUIZ SESSION] Started new session {new_session.id} for rule_set {rule_set.id} (user={new_session.user_id}, total_questions={new_session.total_questions})")
                        # Stocker l'ID de session dans la session Flask pour ce namespace utilisateur+set
                        session_key_session_id = f"quiz_session_id:{user_ns}:{rule_set.slug}"
                        session[session_key_session_id] = new_session.id
                        print(f"[QUIZ SESSION] Stored session id in flask session under key='{session_key_session_id}' -> {new_session.id}")
                    except Exception:
                        db.session.rollback()

            total_questions = len(playlist)
            index = int(session.get(playlist_index_key, 0) or 0)

            # Si terminé: fin du quiz
            if index >= total_questions:
                # Récupérer le nombre de bonnes réponses depuis la session
                total_correct_answers = int(session.get(correct_answers_session_key, 0) or 0)
                total_score = int(session.get(score_session_key, 0) or 0)
                total_questions = len(playlist)

                perfect_bonus_added = False
                perfect_bonus_value = 0
                if rule_set and rule_set.perfect_quiz_bonus and perfect_session_key:
                    perfect_bonus_value = int(rule_set.perfect_quiz_bonus or 0)
                    is_perfect = total_questions > 0 and total_correct_answers == total_questions
                    already_awarded = bool(session.get(perfect_session_key))
                    if is_perfect and perfect_bonus_value > 0 and not already_awarded:
                        total_score += perfect_bonus_value
                        session[score_session_key] = total_score
                        session[perfect_session_key] = True
                        perfect_bonus_added = True
                        if breakdown_session_key:
                            bonus_event = {
                                'type': 'perfect_bonus',
                                'label': 'Bonus quiz parfait',
                                'value': perfect_bonus_value,
                                'total_awarded': perfect_bonus_value,
                            }
                            _append_score_breakdown(breakdown_session_key, bonus_event)
                score_breakdown = list(session.get(breakdown_session_key, [])) if breakdown_session_key else []

                # Clore la UserQuizSession comme completed si présente
                if getattr(g, 'current_user', None):
                    try:
                        session_key_session_id = f"quiz_session_id:{user_ns}:{rule_set.slug}"
                        sess_id = session.get(session_key_session_id)
                        if not sess_id:
                            print(f"[QUIZ SESSION] No session id found in flask session for key='{session_key_session_id}' during quiz completion.")
                        if sess_id:
                            s = UserQuizSession.query.get(sess_id)
                            if s and s.status == 'in_progress':
                                print(
                                    f"[QUIZ SESSION] Updating session {s.id} (user={s.user_id}) before marking completed: "
                                    f"answered={s.answered_count}, total={s.total_questions}, correct={s.correct_count}, score={s.total_score}"
                                )
                                s.status = 'completed'
                                s.answered_count = s.total_questions
                                s.correct_count = total_correct_answers
                                s.total_score = total_score
                                s.updated_at = datetime.utcnow()
                                db.session.commit()
                                print(
                                    f"[QUIZ SESSION] Session {s.id} marked completed at quiz end: "
                                    f"answered={s.answered_count}, correct={s.correct_count}, score={s.total_score}"
                                )
                            else:
                                print(f"[QUIZ SESSION] Expected in-progress session for sess_id={sess_id}, found status={s.status if s else 'missing'} (user={g.current_user.id}).")
                    except Exception:
                        db.session.rollback()
                
                # Si perfect bonus obtenu, afficher l'animation d'abord
                if perfect_bonus_added:
                    return render_template(
                        'quiz_perfect_animation.html',
                        rule_set=rule_set,
                        total_questions=total_questions,
                        total_correct_answers=total_correct_answers,
                        perfect_bonus_value=perfect_bonus_value,
                        history=history_raw or ''
                    )
                
                return render_template(
                    'quiz_final.html',
                    rule_set=rule_set,
                    total_questions=total_questions,
                    total_score=total_score,
                    total_correct_answers=total_correct_answers,
                    perfect_bonus_added=perfect_bonus_added,
                    perfect_bonus_value=perfect_bonus_value,
                    score_breakdown=score_breakdown,
                    history=history_raw or '',
                    quick_double_click=quick_double_click
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

        # Si on sort du mode set (pas de rule_set), marquer toute session in_progress comme abandonnée
        if not rule_set and getattr(g, 'current_user', None):
            try:
                # Abandonner toutes sessions en cours (tous sets) si l'utilisateur a quitté le set
                in_prog = UserQuizSession.query.filter_by(user_id=g.current_user.id, status='in_progress').all()
                for s in in_prog:
                    print(f"[QUIZ SESSION] Abandon session {s.id} after leaving rule_set context in /api/quiz/next (user={s.user_id})")
                    s.status = 'abandoned'
                    s.updated_at = datetime.utcnow()
                if in_prog:
                    db.session.commit()
            except Exception:
                db.session.rollback()

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

        # Mélanger les propositions de réponses pour éviter que la bonne réponse soit toujours à la même position
        if question and question.possible_answers:
            try:
                original_answers = question.possible_answers.split('|||')
                num_answers = len(original_answers)

                # Vérifications de sécurité
                if num_answers == 0:
                    print(f"[QUIZ SHUFFLE] Question {question.id} has no answers, skipping shuffle")
                    return

                # Convertir correct_answer en int si c'est une chaîne
                try:
                    correct_answer_int = int(question.correct_answer)
                    if correct_answer_int < 1 or correct_answer_int > num_answers:
                        print(f"[QUIZ SHUFFLE] Question {question.id} has invalid correct_answer: {question.correct_answer} (should be 1-{num_answers}), skipping shuffle")
                        return
                    else:
                        question.correct_answer = correct_answer_int  # Mettre à jour pour être sûr
                except (ValueError, TypeError):
                    print(f"[QUIZ SHUFFLE] Question {question.id} has invalid correct_answer type: {type(question.correct_answer)} value: {question.correct_answer}, skipping shuffle")
                    return

                # Créer une liste d'indices [0, 1, 2, ...] et la mélanger
                answer_indices = list(range(num_answers))
                random.shuffle(answer_indices)

                # Créer les réponses dans l'ordre mélangé
                shuffled_answers = [original_answers[i] for i in answer_indices]

                # Stocker l'ordre de mélange en session pour cette question (clé par question_id)
                shuffle_key = f"question_shuffle_{question.id}"
                session[shuffle_key] = answer_indices

                # Remplacer temporairement les réponses dans l'objet question pour le template
                question._shuffled_answers = shuffled_answers

                # Calculer la nouvelle position de la bonne réponse (1-based pour correspondre à correct_answer)
                original_correct_index = question.correct_answer - 1  # 0-based
                new_correct_position = answer_indices.index(original_correct_index) + 1  # 1-based
                question._shuffled_correct_answer = new_correct_position

                # Calculer les indices originaux pour chaque position mélangée (pour les images)
                question._original_indices = answer_indices

                print(f"[QUIZ SHUFFLE] Question {question.id}: shuffled {num_answers} answers, correct answer moved from position {question.correct_answer} to {new_correct_position}")
            except Exception as e:
                print(f"[QUIZ SHUFFLE] Error shuffling answers for question {question.id}: {str(e)}, skipping shuffle")
                # En cas d'erreur, on continue sans mélanger

        return render_template('quiz_question.html',
                             question=question,
                             history=history_raw,
                             rule_set=rule_set,
                             current_question_num=current_question_num,
                             total_questions=total_questions,
                             total_score=total_score,
                             quick_double_click=quick_double_click)
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/quiz/final')
def show_quiz_final():
    """Affiche le récapitulatif final du quiz (utilisé après l'animation perfect)."""
    try:
        params = request.args
        rule_set_slug = (params.get('rule_set') or '').strip()
        history_raw = (params.get('history') or '').strip()
        
        rule_set = None
        if rule_set_slug:
            rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
        
        if not rule_set:
            return "Set de règles introuvable", 404
        
        (
            playlist_session_key,
            playlist_index_key,
            score_session_key,
            correct_answers_session_key,
            breakdown_session_key,
            streak_session_key,
            perfect_session_key,
            user_ns,
        ) = _quiz_session_keys(rule_set.slug)
        
        total_correct_answers = int(session.get(correct_answers_session_key, 0) or 0)
        total_score = int(session.get(score_session_key, 0) or 0)
        playlist = session.get(playlist_session_key) or []
        total_questions = len(playlist)
        score_breakdown = list(session.get(breakdown_session_key, [])) if breakdown_session_key else []
        perfect_bonus_added = bool(session.get(perfect_session_key))
        perfect_bonus_value = int(rule_set.perfect_quiz_bonus or 0) if perfect_bonus_added else 0
        
        quick_double_click = bool(session.get('quick_double_click_enabled', False))
        
        return render_template(
            'quiz_final.html',
            rule_set=rule_set,
            total_questions=total_questions,
            total_score=total_score,
            total_correct_answers=total_correct_answers,
            perfect_bonus_added=perfect_bonus_added,
            perfect_bonus_value=perfect_bonus_value,
            score_breakdown=score_breakdown,
            history=history_raw or '',
            quick_double_click=quick_double_click
        )
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/quiz/cancel', methods=['POST'])
def cancel_quiz_session():
    """Marque la session de quiz en cours comme abandonnée pour l'utilisateur connecté et le set fourni."""
    try:
        if not getattr(g, 'current_user', None):
            return "Non connecté", 401
        rule_set_slug = (request.form.get('rule_set') or '').strip()
        if not rule_set_slug:
            return "Paramètre 'rule_set' manquant", 400
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
        if not rule_set:
            return "Set inconnu", 404
        _, _, _, _, _, _, _, user_ns = _quiz_session_keys(rule_set.slug)
        session_key_session_id = f"quiz_session_id:{user_ns}:{rule_set.slug}"
        sess_id = session.get(session_key_session_id)
        if not sess_id:
            return "Aucune session en cours", 200
        s = UserQuizSession.query.get(sess_id)
        if s and s.status == 'in_progress':
            print(f"[QUIZ SESSION] Cancel request abandoning session {s.id} for rule_set {rule_set.id} (user={s.user_id})")
            s.status = 'abandoned'
            s.updated_at = datetime.utcnow()
            db.session.commit()
        return "OK", 200
    except Exception as e:
        db.session.rollback()
        return { 'error': str(e) }, 400




def _calculate_score(rule_set, question, is_correct):
    """Calcule le score de la question et retourne le détail du calcul."""
    breakdown = {
        'type': 'question',
        'question_id': question.id if question else None,
        'question_label': (question.question_text[:120] + '…') if (question and question.question_text and len(question.question_text) > 120) else (question.question_text if question else ''),
        'difficulty': question.difficulty_level if question else None,
        'was_correct': bool(is_correct),
        'base_points': rule_set.scoring_base_points if rule_set and rule_set.scoring_base_points is not None else 0,
        'difficulty_bonus': 0,
        'difficulty_multiplier': 1.0,
        'question_points': 0,
        'combo_bonus': 0,
        'total_awarded': 0,
        'combo_streak': 0,
        'question_index': None,
    }

    if not rule_set or not is_correct:
        return 0, breakdown

    base_points = breakdown['base_points']
    points = base_points

    if rule_set.scoring_difficulty_bonus_type == 'add':
        bonus_map = rule_set.get_difficulty_bonus_map()
        bonus = bonus_map.get(str(question.difficulty_level), 0) if question else 0
        breakdown['difficulty_bonus'] = bonus
        points += bonus
    elif rule_set.scoring_difficulty_bonus_type == 'mult':
        coeff_map = rule_set.get_difficulty_bonus_map()
        coeff = coeff_map.get(str(question.difficulty_level), 1.0) if question else 1.0
        try:
            coeff = float(coeff)
        except (TypeError, ValueError):
            coeff = 1.0
        points = int(round(base_points * coeff))
        breakdown['difficulty_multiplier'] = coeff
        breakdown['difficulty_bonus'] = points - base_points

    breakdown['question_points'] = int(points)
    breakdown['total_awarded'] = int(points)

    return int(points), breakdown


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
        quick_double_click_raw = request.form.get('quick_double_click')
        if quick_double_click_raw is not None:
            quick_double_click = quick_double_click_raw.strip().lower() == 'true'
            session['quick_double_click_enabled'] = quick_double_click
        elif 'quick_double_click_enabled' in session:
            quick_double_click = bool(session.get('quick_double_click_enabled'))
        else:
            quick_double_click = _get_user_double_click_preference()
            session['quick_double_click_enabled'] = quick_double_click

        if not question_id_raw.isdigit():
            return "Identifiant de question invalide", 400

        question = Question.query.options(
            db.joinedload(Question.images),
            db.joinedload(Question.detailed_answer_image),
            db.joinedload(Question.answer_image_links).joinedload(AnswerImageLink.image)
        ).get_or_404(int(question_id_raw))

        # Vérifier si les réponses ont été mélangées pour cette question
        shuffle_key = f"question_shuffle_{question.id}"
        shuffle_order = session.get(shuffle_key)

        if shuffle_order and selected_answer and selected_answer.isdigit():
            # Convertir l'index sélectionné (dans l'ordre mélangé, 1-based) vers l'index original (1-based)
            selected_index_mixed = int(selected_answer) - 1  # 0-based
            original_index = shuffle_order[selected_index_mixed] + 1  # 1-based
            selected_answer_original = str(original_index)
        else:
            selected_answer_original = selected_answer

        correct_value = (question.correct_answer or '').strip()
        # Si pas de réponse (timer expiré ou non sélection), considérer comme faux
        is_correct = bool(selected_answer_original) and (selected_answer_original == correct_value)

        # Debug logging
        print(f"[QUIZ ANSWER] Question ID: {question_id_raw}, Selected: '{selected_answer}', Correct: '{correct_value}', Is correct: {is_correct}")

        # Charger le set de règles si spécifié
        rule_set = None
        playlist_session_key = playlist_index_key = score_session_key = correct_answers_session_key = breakdown_session_key = streak_session_key = perfect_session_key = user_ns = None
        if rule_set_slug:
            rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
            if rule_set:
                (
                    playlist_session_key,
                    playlist_index_key,
                    score_session_key,
                    correct_answers_session_key,
                    breakdown_session_key,
                    streak_session_key,
                    perfect_session_key,
                    user_ns,
                ) = _quiz_session_keys(rule_set.slug)

        # Calculer le score selon les règles
        score = 0
        breakdown = None
        combo_triggered = False
        combo_bonus = 0
        combo_streak = 0
        if rule_set:
            history_ids = []
            if history_raw:
                for token in history_raw.split(','):
                    token = token.strip()
                    if token.isdigit():
                        history_ids.append(int(token))
            question_index = len(history_ids) + 1
            question_score, breakdown = _calculate_score(rule_set, question, is_correct)

            streak_after = 0
            if rule_set.combo_bonus_enabled and rule_set.combo_step and rule_set.combo_bonus_points:
                combo_step = max(int(rule_set.combo_step), 0)
                combo_points = int(rule_set.combo_bonus_points or 0)
                current_streak = int(session.get(streak_session_key, 0) or 0) if streak_session_key else 0
                if is_correct and combo_step > 0 and combo_points > 0:
                    current_streak += 1
                    if current_streak % combo_step == 0:
                        combo_bonus = combo_points
                        combo_triggered = True
                else:
                    current_streak = 0
                streak_after = current_streak
                combo_streak = streak_after
                if streak_session_key:
                    session[streak_session_key] = current_streak
            else:
                if streak_session_key:
                    session[streak_session_key] = 0

            if breakdown:
                breakdown['question_index'] = question_index
                breakdown['combo_bonus'] = combo_bonus
                breakdown['combo_triggered'] = combo_triggered
                breakdown['combo_streak'] = streak_after
                breakdown['total_awarded'] = int(breakdown.get('question_points', 0) + combo_bonus)
                score = breakdown['total_awarded']
            else:
                score = question_score + combo_bonus

            if breakdown_session_key and breakdown:
                _append_score_breakdown(breakdown_session_key, breakdown)

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
            stat.last_selected_answer = selected_answer_original
            stat.last_is_correct = is_correct
            stat.last_answered_at = datetime.utcnow()

        # Mettre à jour la distribution des réponses (QuestionAnswerStat)
        try:
            if selected_answer_original and selected_answer_original.isdigit():
                idx = int(selected_answer_original)
                qa = QuestionAnswerStat.query.filter_by(question_id=question.id, answer_index=idx).first()
                if not qa:
                    qa = QuestionAnswerStat(question_id=question.id, answer_index=idx, selected_count=0)
                    db.session.add(qa)
                qa.selected_count = (qa.selected_count or 0) + 1
        except Exception:
            # Ne pas bloquer la réponse si l'agg échoue
            db.session.rollback()

        db.session.commit()

        # Mettre à jour le score total et le nombre de bonnes réponses en session (namespace user)
        if rule_set and score_session_key and correct_answers_session_key:
            total_score_session = int(session.get(score_session_key, 0) or 0)
            if score:
                total_score_session += int(score)
            session[score_session_key] = total_score_session

            # Compter les bonnes réponses
            total_correct_answers_session = int(session.get(correct_answers_session_key, 0) or 0)
            if is_correct:
                total_correct_answers_session += 1
            session[correct_answers_session_key] = total_correct_answers_session

        # Mettre à jour la progression de playlist (si set de règles, namespace user)
        if rule_set and playlist_session_key and playlist_index_key:
            index = int(session.get(playlist_index_key, 0) or 0)
            playlist = session.get(playlist_session_key) or []
            # Avancer l'index si la question correspond à l'élément courant
            if index < len(playlist) and playlist[index] == question.id:
                session[playlist_index_key] = index + 1

            # Mettre à jour la UserQuizSession si présente
            if getattr(g, 'current_user', None):
                try:
                    session_key_session_id = f"quiz_session_id:{user_ns}:{rule_set.slug}"
                    sess_id = session.get(session_key_session_id)
                    if not sess_id:
                        print(f"[QUIZ SESSION] No session id found in flask session for key='{session_key_session_id}' during answer update.")
                    if sess_id:
                        s = UserQuizSession.query.get(sess_id)
                        if s and s.status == 'in_progress':
                            before_answered = s.answered_count or 0
                            before_correct = s.correct_count or 0
                            before_score = s.total_score or 0
                            print(
                                f"[QUIZ SESSION] Answer update for session {s.id} (user={s.user_id}): "
                                f"answered={before_answered}, total={s.total_questions}, correct={before_correct}, score={before_score}"
                            )
                            s.answered_count = min((s.answered_count or 0) + 1, s.total_questions or 0)
                            if is_correct:
                                s.correct_count = (s.correct_count or 0) + 1
                            # total_score est déjà mis à jour en session; l'appliquer si on a un score crédité
                            if score:
                                s.total_score = (s.total_score or 0) + int(score)
                            if (s.total_questions or 0) > 0 and s.answered_count >= (s.total_questions or 0):
                                s.status = 'completed'
                                print(f"[QUIZ SESSION] Session {s.id} reached completion via answer handler.")
                            s.updated_at = datetime.utcnow()
                            db.session.commit()
                            print(
                                f"[QUIZ SESSION] Post-answer session {s.id}: "
                                f"status={s.status}, answered={s.answered_count}, correct={s.correct_count}, score={s.total_score}"
                            )
                        else:
                            print(f"[QUIZ SESSION] Retrieved session {getattr(s, 'id', None)} but status={getattr(s, 'status', None)} during answer update (expected in_progress).")
                except Exception:
                    db.session.rollback()

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
            (
                playlist_session_key,
                playlist_index_key,
                score_session_key,
                correct_answers_session_key,
                breakdown_session_key,
                streak_session_key,
                perfect_session_key,
                user_ns,
            ) = _quiz_session_keys(rule_set.slug)
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
            selected=selected_answer_original,
            history=next_history,
            rule_set=rule_set,
            score=score,
            combo_triggered=combo_triggered,
            combo_bonus=combo_bonus,
            combo_streak=combo_streak,
            current_question_num=current_question_num,
            total_questions=total_questions,
            total_score=total_score,
            is_timeout=is_timeout,
            quick_double_click=quick_double_click
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


@app.route('/quiz-rule/<int:rule_id>/stats')
def quiz_rule_stats_page(rule_id: int):
    """Page admin des statistiques d'un set de règles."""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    rule = QuizRuleSet.query.get_or_404(rule_id)

    # Sessions liées à ce set
    q_sessions = UserQuizSession.query.filter_by(rule_set_id=rule.id).all()
    total_played = len(q_sessions)
    completed_sessions = [s for s in q_sessions if s.status == 'completed']
    abandoned_sessions = [s for s in q_sessions if s.status == 'abandoned']
    total_completed = len(completed_sessions)

    # Scores
    scores = [s.total_score or 0 for s in completed_sessions]
    avg_score = (sum(scores) / len(scores)) if scores else 0.0
    best_score = max(scores) if scores else 0
    worst_score = min(scores) if scores else 0

    # Bonnes réponses moyennes
    corrects = [s.correct_count or 0 for s in completed_sessions]
    avg_correct = (sum(corrects) / len(corrects)) if corrects else 0.0

    # Joueurs et nombre de sessions jouées
    from collections import Counter
    user_counts = Counter([s.user_id for s in q_sessions if s.user_id])
    players = []
    if user_counts:
        users = User.query.filter(User.id.in_(list(user_counts.keys()))).all()
        id_to_user = {u.id: u for u in users}
        players = [{'user': id_to_user.get(uid), 'count': cnt} for uid, cnt in user_counts.items()]
        # Trier par nombre décroissant
        players.sort(key=lambda x: x['count'], reverse=True)

    return render_template('quiz_rule_stats.html',
                           rule=rule,
                           total_played=total_played,
                           total_completed=total_completed,
                           total_abandoned=len(abandoned_sessions),
                           avg_score=avg_score,
                           best_score=best_score,
                           worst_score=worst_score,
                           avg_correct=avg_correct,
                           players=players)


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
        'success_message': 'Félicitations ! 🎉',
        'question_order_mode': 'difficulty_ascending'
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
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.title).all()
    
    # Charger les valeurs par défaut
    defaults = _load_quiz_rule_defaults()

    return render_template('quiz_rule_form.html', rule=None, themes=themes, specific_themes=specific_themes, countries=countries, images=images, defaults=defaults)


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
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.title).all()
    return render_template('quiz_rule_form.html', rule=rule, themes=themes, specific_themes=specific_themes, countries=countries, images=images, defaults={})


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
        order_mode = (data.get('question_order_mode') or 'difficulty_ascending').strip() or 'difficulty_ascending'
        if order_mode not in ['difficulty_ascending', 'full_shuffle']:
            order_mode = 'difficulty_ascending'

        created_by_user_id = g.current_user.id if getattr(g, 'current_user', None) else None
        rule = QuizRuleSet(
            name=name,
            slug=slug,
            description=(data.get('description') or '').strip() or None,
            comment=(data.get('comment') or '').strip() or None,
            is_active=(data.get('is_active') == 'on'),
            created_by_user_id=created_by_user_id,
            timer_seconds=int(data.get('timer_seconds') or 30),
            use_all_countries=(data.get('use_all_countries') == 'on'),
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
            question_order_mode=order_mode
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

        # Pays autorisés (si non tous)
        if not rule.use_all_countries:
            ids = [int(x) for x in data.getlist('allowed_country_ids') if (x or '').isdigit()]
            if ids:
                rule.allowed_countries = Country.query.filter(Country.id.in_(ids)).all()

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
        rule.use_all_countries = (data.get('use_all_countries') == 'on')
        rule.use_all_broad_themes = (data.get('use_all_broad_themes') == 'on')
        rule.use_all_specific_themes = (data.get('use_all_specific_themes') == 'on')
        rule.scoring_base_points = int(data.get('scoring_base_points') or rule.scoring_base_points or 1)
        rule.scoring_difficulty_bonus_type = (data.get('scoring_difficulty_bonus_type') or rule.scoring_difficulty_bonus_type or 'none')
        rule.combo_bonus_enabled = (data.get('combo_bonus_enabled') == 'on')
        rule.combo_step = (int(data.get('combo_step')) if data.get('combo_step') else None)
        rule.combo_bonus_points = (int(data.get('combo_bonus_points')) if data.get('combo_bonus_points') else None)
        rule.perfect_quiz_bonus = int(data.get('perfect_quiz_bonus') or rule.perfect_quiz_bonus or 0)
        rule.min_correct_answers_to_win = int(data.get('min_correct_answers_to_win') or rule.min_correct_answers_to_win or 0)
        order_mode = (data.get('question_order_mode') or rule.question_order_mode or 'difficulty_ascending').strip()
        if order_mode not in ['difficulty_ascending', 'full_shuffle']:
            order_mode = 'difficulty_ascending'
        rule.question_order_mode = order_mode

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

        # Pays autorisés (si non tous)
        if rule.use_all_countries:
            rule.allowed_countries = []
        else:
            ids = [int(x) for x in data.getlist('allowed_country_ids') if (x or '').isdigit()]
            rule.allowed_countries = Country.query.filter(Country.id.in_(ids)).all() if ids else []

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
    country_ids = request.args.getlist('country_ids[]', type=int)
    filter_by_countries = request.args.get('filter_by_countries') == '1'
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

        # Filtrer par pays si demandé
        if filter_by_countries:
            # Si filter_by_countries est présent, on filtre selon les pays sélectionnés
            if country_ids:
                # Questions qui ont au moins un des pays sélectionnés (évite les doublons)
                query = query.filter(Question.countries.any(Country.id.in_(country_ids)))
            else:
                # Aucun pays sélectionné = seulement les questions générales (sans pays)
                query = query.filter(~Question.countries.any())

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
    country_ids = request.args.getlist('country_ids[]', type=int)
    filter_by_countries = request.args.get('filter_by_countries') == '1'
    specific_theme_ids = request.args.getlist('specific_theme_ids[]', type=int)
    difficulty_levels = request.args.getlist('difficulty_levels[]', type=int)

    if not specific_theme_ids or not difficulty_levels:
        return {'questions': [], 'message': 'Sélectionnez au moins un sous-thème et une difficulté'}

    try:
        # Récupérer les questions qui correspondent aux critères
        query = Question.query.filter(
            Question.specific_theme_id.in_(specific_theme_ids),
            Question.difficulty_level.in_(difficulty_levels)
        )

        # Filtrer par pays si demandé
        if filter_by_countries:
            # Si filter_by_countries est présent, on filtre selon les pays sélectionnés
            if country_ids:
                # Questions qui ont au moins un des pays sélectionnés (évite les doublons)
                query = query.filter(Question.countries.any(Country.id.in_(country_ids)))
            else:
                # Aucun pays sélectionné = seulement les questions générales (sans pays)
                query = query.filter(~Question.countries.any())

        questions = query.order_by(Question.specific_theme_id, Question.difficulty_level, Question.id).all()

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

