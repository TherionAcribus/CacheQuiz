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
from admin_quiz_rules import _slugify, quiz_rules_page, list_quiz_rules, quiz_rule_stats_page, _load_quiz_rule_defaults, new_quiz_rule, edit_quiz_rule, create_quiz_rule, update_quiz_rule, delete_quiz_rule, check_quiz_rule_name, check_quiz_rule_slug, count_questions_for_rule, get_questions_for_selection
from quiz_sharing import create_quiz_share_link, show_share_page, track_share_click, _parse_bool_param
from messaging import messages_home, api_messages_list, api_messages_thread, api_messages_mark_unread, api_messages_delete, api_messages_send, contact_page, report_form, report_submit
from user_features import forgot_password, reset_password, me_page, toggle_save_question, check_question_saved, saved_questions_page, preferences, delete_account
from quiz_playlist_generation import _apply_quiz_filters, _interleave_round_robin, _get_user_answered_keywords, _select_questions_with_keyword_logic, _generate_quiz_playlist
from quiz_gameplay import next_quiz_question, show_quiz_final, cancel_quiz_session, submit_quiz_answer, _quiz_session_keys, _append_score_breakdown, _get_user_double_click_preference, _calculate_score

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

# Quiz gameplay routes
app.add_url_rule('/api/quiz/next', 'next_quiz_question', next_quiz_question)
app.add_url_rule('/api/quiz/final', 'show_quiz_final', show_quiz_final)
app.add_url_rule('/api/quiz/cancel', 'cancel_quiz_session', cancel_quiz_session, methods=['POST'])
app.add_url_rule('/api/quiz/answer', 'submit_quiz_answer', submit_quiz_answer, methods=['POST'])
# Routes pour la gestion des règles du quiz
app.add_url_rule('/quiz-rules', 'quiz_rules_page', quiz_rules_page)
app.add_url_rule('/api/quiz-rules', 'list_quiz_rules', list_quiz_rules)
app.add_url_rule('/quiz-rule/<int:rule_id>/stats', 'quiz_rule_stats_page', quiz_rule_stats_page)
app.add_url_rule('/quiz-rule/new', 'new_quiz_rule', new_quiz_rule)
app.add_url_rule('/quiz-rule/<int:rule_id>/edit', 'edit_quiz_rule', edit_quiz_rule, methods=['GET'])
app.add_url_rule('/api/quiz-rule', 'create_quiz_rule', create_quiz_rule, methods=['POST'])
app.add_url_rule('/api/quiz-rule/<int:rule_id>', 'update_quiz_rule', update_quiz_rule, methods=['PUT', 'POST'])
app.add_url_rule('/api/quiz-rule/<int:rule_id>', 'delete_quiz_rule', delete_quiz_rule, methods=['DELETE'])
app.add_url_rule('/api/quiz-rule/check-name', 'check_quiz_rule_name', check_quiz_rule_name, methods=['GET'])
app.add_url_rule('/api/quiz-rule/check-slug', 'check_quiz_rule_slug', check_quiz_rule_slug, methods=['GET'])
app.add_url_rule('/api/quiz-rule/count-questions', 'count_questions_for_rule', count_questions_for_rule, methods=['GET'])
app.add_url_rule('/api/quiz-rule/get-questions', 'get_questions_for_selection', get_questions_for_selection, methods=['GET'])

# Messaging routes
app.add_url_rule('/messages', 'messages_home', messages_home)
app.add_url_rule('/api/messages/list', 'api_messages_list', api_messages_list)
app.add_url_rule('/api/messages/thread/<int:conv_id>', 'api_messages_thread', api_messages_thread)
app.add_url_rule('/api/messages/mark-unread/<int:conv_id>', 'api_messages_mark_unread', api_messages_mark_unread, methods=['POST'])
app.add_url_rule('/api/messages/delete/<int:conv_id>', 'api_messages_delete', api_messages_delete, methods=['POST'])
app.add_url_rule('/api/messages/send', 'api_messages_send', api_messages_send, methods=['POST'])
app.add_url_rule('/contact', 'contact_page', contact_page, methods=['GET', 'POST'])
app.add_url_rule('/api/report/form', 'report_form', report_form)
app.add_url_rule('/api/report/submit', 'report_submit', report_submit, methods=['POST'])

# User features routes
app.add_url_rule('/forgot-password', 'forgot_password', forgot_password, methods=['GET', 'POST'])
app.add_url_rule('/reset-password/<token>', 'reset_password', reset_password, methods=['GET', 'POST'])
app.add_url_rule('/me', 'me_page', me_page)
app.add_url_rule('/api/questions/<int:question_id>/save', 'toggle_save_question', toggle_save_question, methods=['POST'])
app.add_url_rule('/api/questions/<int:question_id>/is-saved', 'check_question_saved', check_question_saved)
app.add_url_rule('/saved-questions', 'saved_questions_page', saved_questions_page)
app.add_url_rule('/preferences', 'preferences', preferences, methods=['GET', 'POST'])
app.add_url_rule('/delete-account', 'delete_account', delete_account, methods=['POST'])


def _get_token_serializer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='password-reset')










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
# Toutes les fonctions de gestion des QuizRuleSet ont été déplacées vers admin_quiz_rules.py


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

