import os
import json
from datetime import datetime
from flask import render_template, request, redirect, url_for, session, g, flash
from models import db, QuizRuleSet, Question, BroadTheme, SpecificTheme, Country, ImageAsset, User, UserQuizSession, Keyword
from auth import _has_perm, _ensure_admin_page_redirect, _ensure_perm_api, _deny_access
from unidecode import unidecode
from collections import Counter


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


def quiz_rules_page():
    """Page d'administration des ensembles de règles du quiz"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('quiz_rules.html')


def list_quiz_rules():
    """Retourner la liste des sets de règles en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    rules = QuizRuleSet.query.order_by(QuizRuleSet.updated_at.desc()).all()
    return render_template('quiz_rules_list.html', rules=rules)


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


def get_questions_for_selection():
    """Récupérer les questions disponibles pour la sélection manuelle"""
    country_ids = request.args.getlist('country_ids[]', type=int)
    filter_by_countries = request.args.get('filter_by_countries') == '1'
    specific_theme_ids = request.args.getlist('specific_theme_ids[]', type=int)
    difficulty_levels = request.args.getlist('difficulty_levels[]', type=int)

    # Paramètres de recherche
    search_query = request.args.get('q', '').strip()
    author_id = request.args.get('author_id', type=int)
    keyword_id = request.args.get('keyword_id', type=int)
    filter_broad_theme_id = request.args.get('broad_theme_id', type=int)
    filter_specific_theme_id = request.args.get('specific_theme_id', type=int)
    filter_difficulty_level = request.args.get('difficulty_level', type=int)

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

        # Filtres de recherche avancée
        if search_query:
            # Jointures nécessaires pour la recherche textuelle
            query = query.join(User, Question.author_id == User.id, isouter=True)\
                         .join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True)\
                         .join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)
            
            query = query.filter(
                db.or_(
                    Question.question_text.contains(search_query),
                    User.username.contains(search_query),
                    BroadTheme.name.contains(search_query),
                    SpecificTheme.name.contains(search_query)
                )
            )

        if author_id:
            query = query.filter(Question.author_id == author_id)
        
        if keyword_id:
            query = query.join(Question.keywords).filter(Keyword.id == keyword_id)

        if filter_broad_theme_id:
            query = query.filter(Question.broad_theme_id == filter_broad_theme_id)

        if filter_specific_theme_id:
            query = query.filter(Question.specific_theme_id == filter_specific_theme_id)

        if filter_difficulty_level:
            query = query.filter(Question.difficulty_level == filter_difficulty_level)

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
