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
from auth import quick_login, logout, widget_login, widget_send_reset, upgrade_account, login_page, register_page, _has_perm, _ensure_admin_page_redirect, _ensure_perm_api, _deny_access, access_denied_page, auth_widget, load_current_user, inject_current_user
from admin_images import images_page, list_images_api, list_images_json, images_gallery_fragment, new_image, edit_image, create_image, update_image, delete_image
from admin_export import export_page, export_download
from admin_themes import list_themes, list_themes_json, list_subthemes_json, list_authors_json, list_difficulties_json, new_theme, edit_theme, create_theme, update_theme, delete_theme, specific_themes_page, list_specific_themes, new_specific_theme, edit_specific_theme, create_specific_theme, update_specific_theme, delete_specific_theme, get_specific_themes_for_broad_theme, themes_unified_page
from admin_analyse import analysis_page, heatmap_data, question_stats_page
from admin_questions import new_question, view_question, edit_question, create_question, get_question_detail, update_question, delete_question, toggle_question_status, search_questions, sort_questions, _apply_sorting, get_stats
from admin_keywords import list_keywords_json, create_keyword
from admin_countries import countries, list_countries_api, new_country, edit_country, create_country, update_country, delete_country
from admin_profiles import profiles_page, list_profiles, new_profile, edit_profile, create_profile, update_profile, delete_profile
from admin_users import users_page, list_users, new_user, edit_user, create_user, update_user, delete_user
from admin_quiz_rules import _slugify, quiz_rules_page, list_quiz_rules, quiz_rule_stats_page, _load_quiz_rule_defaults, new_quiz_rule, edit_quiz_rule, create_quiz_rule, update_quiz_rule, delete_quiz_rule, check_quiz_rule_name, check_quiz_rule_slug, count_questions_for_rule, get_questions_for_selection, approve_quiz_publication, reject_quiz_publication
from admin_validation import admin_validation_page, list_pending_questions, list_pending_quiz_rules, approve_question_validation, reject_question_validation
from quiz_interface import play_quiz_with_rules, play_quiz, play_quiz_by_slug
from quiz_sharing import create_quiz_share_link, show_share_page, track_share_click, _parse_bool_param
from messaging import messages_home, api_messages_list, api_messages_thread, api_messages_mark_unread, api_messages_delete, api_messages_send, contact_page, report_form, report_submit
from user_features import forgot_password, reset_password, me_page, toggle_save_question, check_question_saved, saved_questions_page, preferences, delete_account
from quiz_playlist_generation import _apply_quiz_filters, _interleave_round_robin, _get_user_answered_keywords, _select_questions_with_keyword_logic, _generate_quiz_playlist
from quiz_gameplay import next_quiz_question, show_quiz_final, cancel_quiz_session, submit_quiz_answer, _quiz_session_keys, _append_score_breakdown, _get_user_double_click_preference, _calculate_score
from file_utils import uploaded_file, sounds_file
from creator_portal import creator_home, creator_access_denied_page
from creator_questions import (
    creator_questions_page,
    list_creator_questions,
    creator_new_question,
    creator_edit_question,
    create_creator_question,
    update_creator_question,
    delete_creator_question,
    request_question_validation,
    confirm_request_question_validation,
)
from creator_images import (
    creator_images_page,
    list_creator_images_api,
    list_creator_images_json,
    creator_images_gallery_fragment,
    creator_new_image,
    creator_edit_image,
    create_creator_image,
    update_creator_image,
    delete_creator_image,
)
from creator_quiz_rules import (
    creator_quiz_rules_page,
    list_creator_quiz_rules,
    creator_new_quiz_rule,
    creator_edit_quiz_rule,
    create_creator_quiz_rule,
    update_creator_quiz_rule,
    delete_creator_quiz_rule,
    request_quiz_publication,
    creator_quiz_rule_count_questions,
    creator_quiz_rule_get_questions_for_selection,
    creator_themes_json,
    creator_subthemes_json,
    creator_authors_json,
    creator_difficulties_json,
    confirm_request_quiz_publication,
)

app = Flask(__name__)

# Configuration selon l'environnement
config_name = os.environ.get('FLASK_ENV') or 'development'
app.config.from_object(config[config_name])
app.config['UPLOAD_FOLDER'] = os.path.join(os.getcwd(), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 10 * 1024 * 1024  # 10MB
app.config['SOUNDS_FOLDER'] = os.path.join(os.getcwd(), 'ressources', 'sounds')

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

db.init_app(app)

# Gestion de session utilisateur
app.before_request(load_current_user)
app.context_processor(inject_current_user)

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

            # Migration pour la table quiz_rule_sets (visibilité/modération)
            result_rules = db.session.execute(text("PRAGMA table_info(quiz_rule_sets)"))
            existing_cols_rules = {row[1] for row in result_rules.fetchall()}
            if 'visibility_status' not in existing_cols_rules:
                db.session.execute(text("ALTER TABLE quiz_rule_sets ADD COLUMN visibility_status TEXT NOT NULL DEFAULT 'public'"))
            if 'public_requested_at' not in existing_cols_rules:
                db.session.execute(text("ALTER TABLE quiz_rule_sets ADD COLUMN public_requested_at DATETIME"))
            if 'public_reviewed_at' not in existing_cols_rules:
                db.session.execute(text("ALTER TABLE quiz_rule_sets ADD COLUMN public_reviewed_at DATETIME"))
            if 'public_reviewed_by_user_id' not in existing_cols_rules:
                db.session.execute(text("ALTER TABLE quiz_rule_sets ADD COLUMN public_reviewed_by_user_id INTEGER"))
            if 'public_review_note' not in existing_cols_rules:
                db.session.execute(text("ALTER TABLE quiz_rule_sets ADD COLUMN public_review_note TEXT"))
            db.session.commit()

            # Migration pour la table images (propriétaire)
            result_images = db.session.execute(text("PRAGMA table_info(images)"))
            existing_cols_images = {row[1] for row in result_images.fetchall()}
            if 'created_by_user_id' not in existing_cols_images:
                db.session.execute(text("ALTER TABLE images ADD COLUMN created_by_user_id INTEGER"))
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


# Auth routes
app.add_url_rule('/auth/quick-login', 'quick_login', quick_login, methods=['POST'])
app.add_url_rule('/auth/logout', 'logout', logout, methods=['POST'])
app.add_url_rule('/auth/widget-login', 'widget_login', widget_login, methods=['POST'])
app.add_url_rule('/auth/widget-send-reset', 'widget_send_reset', widget_send_reset, methods=['POST'])
app.add_url_rule('/auth/upgrade-account', 'upgrade_account', upgrade_account, methods=['POST'])
app.add_url_rule('/login', 'login_page', login_page, methods=['GET', 'POST'])
app.add_url_rule('/register', 'register_page', register_page, methods=['GET', 'POST'])
app.add_url_rule('/access-denied', 'access_denied_page', access_denied_page)
app.add_url_rule('/auth/widget', 'auth_widget', auth_widget)

# Creator portal routes
app.add_url_rule('/creator', 'creator_home', creator_home)
app.add_url_rule('/creator/access-denied', 'creator_access_denied_page', creator_access_denied_page)
app.add_url_rule('/creator/questions', 'creator_questions_page', creator_questions_page)
app.add_url_rule('/api/creator/questions', 'list_creator_questions', list_creator_questions)
app.add_url_rule('/creator/question/new', 'creator_new_question', creator_new_question)
app.add_url_rule('/creator/question/<int:question_id>/edit', 'creator_edit_question', creator_edit_question, methods=['GET'])
app.add_url_rule('/api/creator/question', 'create_creator_question', create_creator_question, methods=['POST'])
app.add_url_rule('/api/creator/question/<int:question_id>', 'update_creator_question', update_creator_question, methods=['POST', 'PUT'])
app.add_url_rule('/api/creator/question/<int:question_id>', 'delete_creator_question', delete_creator_question, methods=['DELETE'])
app.add_url_rule('/api/creator/question/<int:question_id>/request-validation', 'request_question_validation', request_question_validation, methods=['POST'])
app.add_url_rule('/api/creator/question/<int:question_id>/request-validation/confirm', 'confirm_request_question_validation', confirm_request_question_validation, methods=['GET'])

# Creator images
app.add_url_rule('/creator/images', 'creator_images_page', creator_images_page)
app.add_url_rule('/api/creator/images', 'list_creator_images_api', list_creator_images_api)
app.add_url_rule('/api/creator/images/json', 'list_creator_images_json', list_creator_images_json)
app.add_url_rule('/api/creator/images/gallery', 'creator_images_gallery_fragment', creator_images_gallery_fragment)
app.add_url_rule('/creator/image/new', 'creator_new_image', creator_new_image)
app.add_url_rule('/creator/image/<int:image_id>/edit', 'creator_edit_image', creator_edit_image, methods=['GET'])

def create_creator_image_wrapper():
    return create_creator_image(app)

def update_creator_image_wrapper(image_id):
    return update_creator_image(image_id, app)

def delete_creator_image_wrapper(image_id):
    return delete_creator_image(image_id, app)

app.add_url_rule('/api/creator/image', 'create_creator_image', create_creator_image_wrapper, methods=['POST'])
app.add_url_rule('/api/creator/image/<int:image_id>', 'update_creator_image', update_creator_image_wrapper, methods=['POST', 'PUT'])
app.add_url_rule('/api/creator/image/<int:image_id>', 'delete_creator_image', delete_creator_image_wrapper, methods=['DELETE'])

# Creator quiz rules
app.add_url_rule('/creator/quiz-rules', 'creator_quiz_rules_page', creator_quiz_rules_page)
app.add_url_rule('/api/creator/quiz-rules', 'list_creator_quiz_rules', list_creator_quiz_rules)
app.add_url_rule('/creator/quiz-rule/new', 'creator_new_quiz_rule', creator_new_quiz_rule)
app.add_url_rule('/creator/quiz-rule/<int:rule_id>/edit', 'creator_edit_quiz_rule', creator_edit_quiz_rule, methods=['GET'])
app.add_url_rule('/api/creator/quiz-rule', 'create_creator_quiz_rule', create_creator_quiz_rule, methods=['POST'])
app.add_url_rule('/api/creator/quiz-rule/<int:rule_id>', 'update_creator_quiz_rule', update_creator_quiz_rule, methods=['POST', 'PUT'])
app.add_url_rule('/api/creator/quiz-rule/<int:rule_id>', 'delete_creator_quiz_rule', delete_creator_quiz_rule, methods=['DELETE'])
app.add_url_rule('/api/creator/quiz-rule/<int:rule_id>/request-public', 'request_quiz_publication', request_quiz_publication, methods=['POST'])
app.add_url_rule('/api/creator/quiz-rule/<int:rule_id>/request-public/confirm', 'confirm_request_quiz_publication', confirm_request_quiz_publication, methods=['GET'])
app.add_url_rule('/api/creator/quiz-rule/count-questions', 'creator_quiz_rule_count_questions', creator_quiz_rule_count_questions, methods=['GET'])
app.add_url_rule('/api/creator/quiz-rule/get-questions', 'creator_quiz_rule_get_questions_for_selection', creator_quiz_rule_get_questions_for_selection, methods=['GET'])

# Creator taxonomy/json endpoints (used by quiz_rule_form in creator mode)
app.add_url_rule('/api/creator/themes/json', 'creator_themes_json', creator_themes_json)
app.add_url_rule('/api/creator/subthemes/json', 'creator_subthemes_json', creator_subthemes_json)
app.add_url_rule('/api/creator/authors/json', 'creator_authors_json', creator_authors_json)
app.add_url_rule('/api/creator/difficulties/json', 'creator_difficulties_json', creator_difficulties_json)

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
app.add_url_rule('/api/stats', 'get_stats', get_stats)

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

# Quiz interface routes
app.add_url_rule('/quiz/<slug>', 'play_quiz_with_rules', play_quiz_with_rules)
app.add_url_rule('/play', 'play_quiz', play_quiz)
app.add_url_rule('/play/<slug>', 'play_quiz_by_slug', play_quiz_by_slug)

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
app.add_url_rule('/api/quiz-rule/<int:rule_id>/review/approve', 'approve_quiz_publication', approve_quiz_publication, methods=['POST'])
app.add_url_rule('/api/quiz-rule/<int:rule_id>/review/reject', 'reject_quiz_publication', reject_quiz_publication, methods=['POST'])

# Admin validation
app.add_url_rule('/admin/validation', 'admin_validation_page', admin_validation_page)
app.add_url_rule('/api/admin/validation/questions', 'list_pending_questions', list_pending_questions)
app.add_url_rule('/api/admin/validation/quiz-rules', 'list_pending_quiz_rules', list_pending_quiz_rules)
app.add_url_rule('/api/admin/validation/question/<int:question_id>/approve', 'approve_question_validation', approve_question_validation, methods=['POST'])
app.add_url_rule('/api/admin/validation/question/<int:question_id>/reject', 'reject_question_validation', reject_question_validation, methods=['POST'])

# Messaging routes
app.add_url_rule('/messages', 'messages_home', messages_home)
app.add_url_rule('/api/messages/list', 'api_messages_list', api_messages_list)
app.add_url_rule('/api/messages/thread/<int:conv_id>', 'api_messages_thread', api_messages_thread)
app.add_url_rule('/api/messages/mark-unread/<int:conv_id>', 'api_messages_mark_unread', api_messages_mark_unread, methods=['POST'])
app.add_url_rule('/api/messages/delete/<int:conv_id>', 'api_messages_delete', api_messages_delete, methods=['POST'])
app.add_url_rule('/api/messages/send', 'api_messages_send', api_messages_send, methods=['POST'])

# File serving routes
app.add_url_rule('/uploads/<path:filename>', 'uploaded_file', uploaded_file)
app.add_url_rule('/sounds/<path:filename>', 'sounds_file', sounds_file)
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

