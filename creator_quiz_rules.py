from datetime import datetime
from flask import render_template, request, g
import uuid

from models import (
    db,
    QuizRuleSet,
    Question,
    BroadTheme,
    SpecificTheme,
    Country,
    ImageAsset,
    Keyword,
    Conversation,
    ConversationParticipant,
    ConversationMessage,
    Profile,
    User,
)
from auth import _ensure_creator_page_redirect, _ensure_creator_api
from email_utils import send_email_optional


def creator_quiz_rules_page():
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp
    return render_template('creator_quiz_rules.html')


def list_creator_quiz_rules():
    denied = _ensure_creator_api()
    if denied:
        return denied

    user = g.current_user
    rules = QuizRuleSet.query.filter_by(created_by_user_id=user.id).order_by(QuizRuleSet.updated_at.desc()).all()
    # Assurer qu'un lien de partage privé peut être affiché (clé générée si manquante)
    try:
        changed = False
        for r in rules:
            if not getattr(r, 'private_access_key', None):
                r.private_access_key = uuid.uuid4().hex
                changed = True
            if not getattr(r, 'question_pool_scope', None):
                r.question_pool_scope = 'all'
                changed = True
        if changed:
            db.session.commit()
    except Exception:
        db.session.rollback()
    return render_template('creator_quiz_rules_list.html', rules=rules)


def creator_new_quiz_rule():
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp

    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.title).all()

    # Valeurs par défaut: réutiliser la fonction existante si dispo
    try:
        from admin_quiz_rules import _load_quiz_rule_defaults
        defaults = _load_quiz_rule_defaults()
    except Exception:
        defaults = {}

    return render_template(
        'quiz_rule_form.html',
        rule=None,
        themes=themes,
        specific_themes=specific_themes,
        countries=countries,
        images=images,
        defaults=defaults,
        creator_mode=True,
        form_action='/api/creator/quiz-rule',
    )


def creator_edit_quiz_rule(rule_id: int):
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp

    rule = QuizRuleSet.query.get_or_404(rule_id)
    user = g.current_user
    if not user or rule.created_by_user_id != user.id:
        return render_template('creator_access_denied_full.html'), 200

    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.title).all()

    return render_template(
        'quiz_rule_form.html',
        rule=rule,
        themes=themes,
        specific_themes=specific_themes,
        countries=countries,
        images=images,
        defaults={},
        creator_mode=True,
        form_action=f'/api/creator/quiz-rule/{rule.id}',
    )


def _eligible_questions_query(user_id: int):
    """Questions utilisables par un créateur dans ses quiz privés: publiques + ses propres (même non publiées/privées)."""
    return Question.query.filter(
        db.or_(
            db.and_(Question.is_published.is_(True), Question.is_private.is_(False)),
            Question.author_id == user_id,
        )
    )


def _normalize_question_pool_scope(raw: str | None) -> str:
    scope = (raw or '').strip().lower()
    return 'mine' if scope in ('mine', 'my', 'mes') else 'all'


def _creator_question_pool_query(creator_user_id: int, scope: str):
    """Pool disponible pour configurer un quiz côté créateur."""
    scope = _normalize_question_pool_scope(scope)
    if scope == 'mine':
        return Question.query.filter(Question.author_id == creator_user_id)
    return _eligible_questions_query(creator_user_id)


def create_creator_quiz_rule():
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied
        user = g.current_user
        data = request.form

        name = (data.get('name') or '').strip()
        if not name:
            return "Nom requis", 400

        # Slug
        slug = (data.get('slug') or '').strip()
        if not slug:
            try:
                from admin_quiz_rules import _slugify
                slug = _slugify(name)
            except Exception:
                slug = name.lower().replace(' ', '-')

        order_mode = (data.get('question_order_mode') or 'difficulty_ascending').strip() or 'difficulty_ascending'
        if order_mode not in ['difficulty_ascending', 'full_shuffle']:
            order_mode = 'difficulty_ascending'

        pool_scope = _normalize_question_pool_scope(data.get('question_pool_scope'))

        rule = QuizRuleSet(
            name=name,
            slug=slug,
            description=(data.get('description') or '').strip() or None,
            comment=(data.get('comment') or '').strip() or None,
            is_active=True,
            created_by_user_id=user.id,
            timer_seconds=int(data.get('timer_seconds') or 30),
            use_all_countries=(data.get('use_all_countries') == 'on'),
            use_all_broad_themes=(data.get('use_all_broad_themes') == 'on'),
            use_all_specific_themes=(data.get('use_all_specific_themes') == 'on'),
            scoring_base_points=int(data.get('scoring_base_points') or 1),
            scoring_difficulty_bonus_type=(data.get('scoring_difficulty_bonus_type') or 'none'),
            combo_bonus_enabled=(data.get('combo_bonus_enabled') == 'on'),
            combo_step=(int(data.get('combo_step')) if (data.get('combo_step') or '').isdigit() else None),
            combo_bonus_points=(int(data.get('combo_bonus_points')) if (data.get('combo_bonus_points') or '').isdigit() else None),
            perfect_quiz_bonus=int(data.get('perfect_quiz_bonus') or 0),
            min_correct_answers_to_win=int(data.get('min_correct_answers_to_win') or 0),
            intro_message=(data.get('intro_message') or '').strip() or None,
            success_message=(data.get('success_message') or '').strip() or None,
            failure_message=(data.get('failure_message') or '').strip() or None,
            intro_image_id=(int(data.get('intro_image_id')) if (data.get('intro_image_id') or '').isdigit() else None),
            success_image_id=(int(data.get('success_image_id')) if (data.get('success_image_id') or '').isdigit() else None),
            failure_image_id=(int(data.get('failure_image_id')) if (data.get('failure_image_id') or '').isdigit() else None),
            question_order_mode=order_mode,
            visibility_status='private',  # forcer privé côté créateur
            question_pool_scope=pool_scope,
        )
        # Générer une clé d'accès pour le partage privé (si manquante)
        rule.private_access_key = rule.private_access_key or uuid.uuid4().hex

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

        # Pays autorisés
        if not rule.use_all_countries:
            ids = [int(x) for x in data.getlist('allowed_country_ids') if (x or '').isdigit()]
            rule.allowed_countries = Country.query.filter(Country.id.in_(ids)).all() if ids else []

        # Thèmes autorisés
        if not rule.use_all_broad_themes:
            ids = [int(x) for x in data.getlist('allowed_broad_theme_ids') if (x or '').isdigit()]
            rule.allowed_broad_themes = BroadTheme.query.filter(BroadTheme.id.in_(ids)).all() if ids else []

        if not rule.use_all_specific_themes:
            ids = [int(x) for x in data.getlist('allowed_specific_theme_ids') if (x or '').isdigit()]
            rule.allowed_specific_themes = SpecificTheme.query.filter(SpecificTheme.id.in_(ids)).all() if ids else []

        # Mode de sélection (auto vs manuel)
        selected_question_ids = [int(x) for x in data.getlist('selected_question_ids') if (x or '').isdigit()]

        # Calculer le pool disponible (critères + eligibilité créateur)
        available_query = _creator_question_pool_query(user.id, pool_scope)
        if not rule.use_all_specific_themes and rule.allowed_specific_themes:
            st_ids = [st.id for st in rule.allowed_specific_themes]
            available_query = available_query.filter(Question.specific_theme_id.in_(st_ids))
        if difficulties:
            available_query = available_query.filter(Question.difficulty_level.in_(difficulties))
        if not rule.use_all_countries:
            c_ids = [c.id for c in rule.allowed_countries]
            if c_ids:
                available_query = available_query.filter(Question.countries.any(Country.id.in_(c_ids)))
            else:
                available_query = available_query.filter(~Question.countries.any())

        available_question_ids = [row[0] for row in available_query.with_entities(Question.id).all()]

        if selected_question_ids and set(selected_question_ids) != set(available_question_ids):
            rule.question_selection_mode = 'manual'
            eligible = _creator_question_pool_query(user.id, pool_scope).filter(Question.id.in_(selected_question_ids)).all()
            rule.selected_questions = eligible
        else:
            rule.question_selection_mode = 'auto'
            rule.selected_questions = []

        db.session.add(rule)
        db.session.commit()

        rules = QuizRuleSet.query.filter_by(created_by_user_id=user.id).order_by(QuizRuleSet.updated_at.desc()).all()
        return render_template('creator_quiz_rules_list.html', rules=rules)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def update_creator_quiz_rule(rule_id: int):
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied
        user = g.current_user
        rule = QuizRuleSet.query.get_or_404(rule_id)
        if rule.created_by_user_id != user.id:
            return "Accès refusé", 403

        data = request.form
        name = (data.get('name') or '').strip()
        if not name:
            return "Nom requis", 400

        rule.name = name
        rule.slug = (data.get('slug') or '').strip() or rule.slug
        rule.description = (data.get('description') or '').strip() or None
        rule.comment = (data.get('comment') or '').strip() or None
        rule.timer_seconds = int(data.get('timer_seconds') or rule.timer_seconds or 30)
        rule.use_all_countries = (data.get('use_all_countries') == 'on')
        rule.use_all_broad_themes = (data.get('use_all_broad_themes') == 'on')
        rule.use_all_specific_themes = (data.get('use_all_specific_themes') == 'on')

        rule.scoring_base_points = int(data.get('scoring_base_points') or rule.scoring_base_points or 1)
        rule.scoring_difficulty_bonus_type = (data.get('scoring_difficulty_bonus_type') or rule.scoring_difficulty_bonus_type or 'none')
        rule.combo_bonus_enabled = (data.get('combo_bonus_enabled') == 'on')
        rule.combo_step = (int(data.get('combo_step')) if (data.get('combo_step') or '').isdigit() else None)
        rule.combo_bonus_points = (int(data.get('combo_bonus_points')) if (data.get('combo_bonus_points') or '').isdigit() else None)
        rule.perfect_quiz_bonus = int(data.get('perfect_quiz_bonus') or rule.perfect_quiz_bonus or 0)
        rule.min_correct_answers_to_win = int(data.get('min_correct_answers_to_win') or rule.min_correct_answers_to_win or 0)

        order_mode = (data.get('question_order_mode') or rule.question_order_mode or 'difficulty_ascending').strip()
        if order_mode not in ['difficulty_ascending', 'full_shuffle']:
            order_mode = 'difficulty_ascending'
        rule.question_order_mode = order_mode

        pool_scope = _normalize_question_pool_scope(data.get('question_pool_scope') or getattr(rule, 'question_pool_scope', None))
        rule.question_pool_scope = pool_scope
        rule.private_access_key = rule.private_access_key or uuid.uuid4().hex

        rule.intro_message = (data.get('intro_message') or '').strip() or None
        rule.success_message = (data.get('success_message') or '').strip() or None
        rule.failure_message = (data.get('failure_message') or '').strip() or None
        rule.intro_image_id = (int(data.get('intro_image_id')) if (data.get('intro_image_id') or '').isdigit() else None)
        rule.success_image_id = (int(data.get('success_image_id')) if (data.get('success_image_id') or '').isdigit() else None)
        rule.failure_image_id = (int(data.get('failure_image_id')) if (data.get('failure_image_id') or '').isdigit() else None)

        # Difficultés / quotas / bonus
        difficulties = [int(x) for x in data.getlist('allowed_difficulties') if (x or '').isdigit()]
        rule.set_allowed_difficulties(difficulties)

        quotas = {}
        for d in range(1, 6):
            val = (data.get(f'questions_per_difficulty_{d}') or '').strip()
            if val.isdigit():
                quotas[str(d)] = int(val)
        rule.set_questions_per_difficulty(quotas)

        bonus_map = {}
        for d in range(1, 6):
            raw = (data.get(f'difficulty_bonus_{d}') or '').strip()
            if raw:
                try:
                    bonus_map[str(d)] = float(raw)
                except Exception:
                    pass
        rule.set_difficulty_bonus_map(bonus_map)

        # Pays / thèmes
        if rule.use_all_countries:
            rule.allowed_countries = []
        else:
            ids = [int(x) for x in data.getlist('allowed_country_ids') if (x or '').isdigit()]
            rule.allowed_countries = Country.query.filter(Country.id.in_(ids)).all() if ids else []

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

        # Mode de sélection (auto vs manuel)
        selected_question_ids = [int(x) for x in data.getlist('selected_question_ids') if (x or '').isdigit()]

        available_query = _creator_question_pool_query(user.id, pool_scope)
        if not rule.use_all_specific_themes and rule.allowed_specific_themes:
            st_ids = [st.id for st in rule.allowed_specific_themes]
            available_query = available_query.filter(Question.specific_theme_id.in_(st_ids))
        if difficulties:
            available_query = available_query.filter(Question.difficulty_level.in_(difficulties))
        if not rule.use_all_countries:
            c_ids = [c.id for c in rule.allowed_countries]
            if c_ids:
                available_query = available_query.filter(Question.countries.any(Country.id.in_(c_ids)))
            else:
                available_query = available_query.filter(~Question.countries.any())

        available_question_ids = [row[0] for row in available_query.with_entities(Question.id).all()]

        if selected_question_ids and set(selected_question_ids) != set(available_question_ids):
            rule.question_selection_mode = 'manual'
            rule.selected_questions = _creator_question_pool_query(user.id, pool_scope).filter(Question.id.in_(selected_question_ids)).all()
        else:
            rule.question_selection_mode = 'auto'
            rule.selected_questions = []

        # Toujours privé/pending/rejected/public gérés via actions dédiées
        if rule.visibility_status not in ('public', 'pending', 'rejected', 'private'):
            rule.visibility_status = 'private'

        rule.updated_at = datetime.utcnow()
        db.session.commit()

        rules = QuizRuleSet.query.filter_by(created_by_user_id=user.id).order_by(QuizRuleSet.updated_at.desc()).all()
        return render_template('creator_quiz_rules_list.html', rules=rules)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def delete_creator_quiz_rule(rule_id: int):
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied
        user = g.current_user
        rule = QuizRuleSet.query.get_or_404(rule_id)
        if rule.created_by_user_id != user.id:
            return "Accès refusé", 403
        db.session.delete(rule)
        db.session.commit()
        rules = QuizRuleSet.query.filter_by(created_by_user_id=user.id).order_by(QuizRuleSet.updated_at.desc()).all()
        return render_template('creator_quiz_rules_list.html', rules=rules)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def confirm_delete_creator_quiz_rule(rule_id: int):
    """Retourne une modale de confirmation (cohérente) pour supprimer un quiz (set de règles)."""
    denied = _ensure_creator_api()
    if denied:
        return denied

    user = g.current_user
    rule = QuizRuleSet.query.get_or_404(rule_id)
    if rule.created_by_user_id != user.id:
        return "Accès refusé", 403

    inner = render_template(
        'creator_confirm_modal.html',
        title="Supprimer le quiz",
        message=f"Confirmez la suppression du quiz « {rule.name} ». Cette action est irréversible.",
        action_url=f"/api/creator/quiz-rule/{rule.id}",
        action_method="delete",
        target_selector="#quiz-rules-list",
        confirm_label="🗑️ Supprimer",
        confirm_button_class="btn-danger",
    )
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"

def _get_admin_users():
    admin_profile = Profile.query.filter_by(name='Administrateur').first()
    if not admin_profile:
        return []
    return User.query.filter_by(profile_id=admin_profile.id, is_active=True).all()


def request_quiz_publication(rule_id: int):
    """Passe le quiz en 'pending' et notifie les admins via messagerie."""
    denied = _ensure_creator_api()
    if denied:
        return denied
    user = g.current_user
    rule = QuizRuleSet.query.get_or_404(rule_id)
    if rule.created_by_user_id != user.id:
        return "Accès refusé", 403

    # Toujours demander depuis private/rejected (idempotent)
    rule.visibility_status = 'pending'
    rule.public_requested_at = datetime.utcnow()
    rule.public_reviewed_at = None
    rule.public_reviewed_by_user_id = None
    rule.public_review_note = None
    rule.updated_at = datetime.utcnow()

    try:
        subject = f"Publication quiz: {rule.name} ({rule.slug})"
        conv = Conversation(subject=subject, context_type='quiz_publication', context_id=rule.id)
        db.session.add(conv)
        db.session.flush()

        db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=user.id, last_read_at=datetime.utcnow()))
        admin_users = _get_admin_users()
        for adm in admin_users:
            db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=adm.id, last_read_at=None))

        msg = ConversationMessage(
            conversation_id=conv.id,
            sender_id=user.id,
            content=(
                "Demande de publication d'un quiz (set de règles).\n\n"
                f"Créateur: {user.username}\n"
                f"Nom: {rule.name}\n"
                f"Slug: {rule.slug}\n"
                f"Statut: {rule.visibility_status}\n"
            ),
        )
        db.session.add(msg)

        db.session.commit()

        # Emails optionnels
        for adm in admin_users:
            prefs = adm.get_preferences()
            notify_enabled = prefs.get('notify_email_on_message', False)
            if notify_enabled and adm.email:
                try:
                    send_email_optional(
                        to_email=adm.email,
                        subject=f"Nouveau message: {subject}",
                        body=f"Une demande de publication de quiz a été envoyée par {user.username}.\n\nAccéder à la conversation: {request.host_url.rstrip('/')}/messages",
                    )
                except Exception:
                    pass

        rules = QuizRuleSet.query.filter_by(created_by_user_id=user.id).order_by(QuizRuleSet.updated_at.desc()).all()
        return render_template('creator_quiz_rules_list.html', rules=rules)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def creator_quiz_rule_count_questions():
    """Compter les questions disponibles selon critères, mais limitées au pool du créateur."""
    denied = _ensure_creator_api()
    if denied:
        return denied
    user = g.current_user

    country_ids = request.args.getlist('country_ids[]', type=int)
    filter_by_countries = request.args.get('filter_by_countries') == '1'
    broad_theme_ids = request.args.getlist('broad_theme_ids[]', type=int)
    use_all_broad_themes = (request.args.get('use_all_broad_themes') == '1')
    specific_theme_ids = request.args.getlist('specific_theme_ids[]', type=int)
    use_all_specific_themes = (request.args.get('use_all_specific_themes') == '1')
    difficulty_levels = request.args.getlist('difficulty_levels[]', type=int)
    scope = _normalize_question_pool_scope(request.args.get('scope'))

    query = _creator_question_pool_query(user.id, scope)

    # Difficultés (optionnel: si vide = toutes)
    if difficulty_levels:
        query = query.filter(Question.difficulty_level.in_(difficulty_levels))

    # Thèmes larges (optionnel)
    if (not use_all_broad_themes) and broad_theme_ids:
        query = query.filter(Question.broad_theme_id.in_(broad_theme_ids))

    # Sous-thèmes: si "tous" => ne pas filtrer (inclut aussi specific_theme_id NULL)
    if not use_all_specific_themes:
        if specific_theme_ids:
            query = query.filter(Question.specific_theme_id.in_(specific_theme_ids))
        else:
            # En mode créateur, on ne bloque pas strictement: laisser l'utilisateur voir ses questions.
            # Si la DB est grosse, l'UI reste contrôlée via les onglets et la sélection.
            pass

    if filter_by_countries:
        if country_ids:
            query = query.filter(Question.countries.any(Country.id.in_(country_ids)))
        else:
            query = query.filter(~Question.countries.any())

    count = query.count()
    if count == 0:
        message = 'Aucune question ne correspond à ces critères'
    elif count == 1:
        message = '1 question disponible'
    else:
        message = f'{count} questions disponibles'
    return {'count': count, 'message': message}


def creator_quiz_rule_get_questions_for_selection():
    """Liste des questions disponibles pour la sélection manuelle (public + propres)."""
    denied = _ensure_creator_api()
    if denied:
        return denied
    user = g.current_user

    country_ids = request.args.getlist('country_ids[]', type=int)
    filter_by_countries = request.args.get('filter_by_countries') == '1'
    broad_theme_ids = request.args.getlist('broad_theme_ids[]', type=int)
    use_all_broad_themes = (request.args.get('use_all_broad_themes') == '1')
    specific_theme_ids = request.args.getlist('specific_theme_ids[]', type=int)
    use_all_specific_themes = (request.args.get('use_all_specific_themes') == '1')
    difficulty_levels = request.args.getlist('difficulty_levels[]', type=int)
    scope = _normalize_question_pool_scope(request.args.get('scope'))

    search_query = (request.args.get('q') or '').strip()
    keyword_id = request.args.get('keyword_id', type=int)
    filter_broad_theme_id = request.args.get('broad_theme_id', type=int)
    filter_specific_theme_id = request.args.get('specific_theme_id', type=int)
    filter_difficulty_level = request.args.get('difficulty_level', type=int)

    query = _creator_question_pool_query(user.id, scope)

    # Difficultés (optionnel)
    if difficulty_levels:
        query = query.filter(Question.difficulty_level.in_(difficulty_levels))

    # Thèmes larges (optionnel)
    if (not use_all_broad_themes) and broad_theme_ids:
        query = query.filter(Question.broad_theme_id.in_(broad_theme_ids))

    # Sous-thèmes (optionnel). Si "tous", on n'applique pas le filtre afin d'inclure aussi NULL.
    if not use_all_specific_themes:
        if specific_theme_ids:
            query = query.filter(Question.specific_theme_id.in_(specific_theme_ids))
        else:
            pass

    if filter_by_countries:
        if country_ids:
            query = query.filter(Question.countries.any(Country.id.in_(country_ids)))
        else:
            query = query.filter(~Question.countries.any())

    if search_query:
        # Confidentialité: côté créateur on n'indexe pas les pseudos joueurs dans la recherche
        query = query.join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True)\
                     .join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)
        query = query.filter(
            db.or_(
                Question.question_text.contains(search_query),
                BroadTheme.name.contains(search_query),
                SpecificTheme.name.contains(search_query),
            )
        )

    if keyword_id:
        query = query.join(Question.keywords).filter(Keyword.id == keyword_id)
    if filter_broad_theme_id:
        query = query.filter(Question.broad_theme_id == filter_broad_theme_id)
    if filter_specific_theme_id:
        query = query.filter(Question.specific_theme_id == filter_specific_theme_id)
    if filter_difficulty_level:
        query = query.filter(Question.difficulty_level == filter_difficulty_level)

    questions = query.order_by(Question.specific_theme_id, Question.difficulty_level, Question.id).all()
    return {
        'questions': [
            {
                'id': q.id,
                'question_text': (q.question_text[:200] + '...') if len(q.question_text) > 200 else q.question_text,
                'broad_theme_name': q.theme.name if q.theme else None,
                'specific_theme_name': q.specific_theme_obj.name if q.specific_theme_obj else None,
                'difficulty_level': q.difficulty_level,
            }
            for q in questions
        ],
        'count': len(questions),
    }


def creator_themes_json():
    denied = _ensure_creator_api()
    if denied:
        return denied
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return [{'id': t.id, 'name': t.name} for t in themes]


def creator_subthemes_json():
    denied = _ensure_creator_api()
    if denied:
        return denied
    broad_theme_id = request.args.get('broad_theme_id', type=int)
    query = SpecificTheme.query
    if broad_theme_id:
        query = query.filter_by(broad_theme_id=broad_theme_id)
    subthemes = query.order_by(SpecificTheme.name).all()
    return [{'id': t.id, 'name': t.name, 'broad_theme_id': t.broad_theme_id} for t in subthemes]


def creator_authors_json():
    """Pour le filtre auteur: côté créateur on ne propose que lui-même."""
    denied = _ensure_creator_api()
    if denied:
        return denied
    user = g.current_user
    return [{'id': user.id, 'username': user.username}]


def creator_difficulties_json():
    denied = _ensure_creator_api()
    if denied:
        return denied
    diffs = db.session.query(Question.difficulty_level).distinct().filter(Question.difficulty_level.isnot(None)).order_by(Question.difficulty_level).all()
    existing = [d[0] for d in diffs] or [1, 2, 3, 4, 5]
    return [{'id': d, 'name': f"Niveau {d}"} for d in existing]


def confirm_request_quiz_publication(rule_id: int):
    """Retourne une modale de confirmation pour demander la publication (review admin)."""
    denied = _ensure_creator_api()
    if denied:
        return denied

    user = g.current_user
    rule = QuizRuleSet.query.get_or_404(rule_id)
    if rule.created_by_user_id != user.id:
        return "Accès refusé", 403

    inner = render_template(
        'creator_confirm_modal.html',
        title="Demander la publication",
        message="Votre quiz restera privé tant qu’un administrateur ne l’aura pas approuvé.",
        action_url=f"/api/creator/quiz-rule/{rule.id}/request-public",
        target_selector="#quiz-rules-list",
        confirm_label="📣 Envoyer la demande",
    )
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"


