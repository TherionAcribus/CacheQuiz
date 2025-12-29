from flask import render_template, request, redirect, url_for, session, g
from models import db, QuizRuleSet, UserQuizSession
from datetime import datetime
from quiz_gameplay import _get_user_double_click_preference
from quiz_playlist_generation import get_rule_set_stats


def play_quiz_with_rules(slug: str):
    """Redirige vers la page de jeu avec un set de règles prédéfini."""
    return redirect(f'/play?rule_set={slug}')


def play_quiz():
    """Page pour choisir un set de règles et jouer au quiz."""
    rule_set = None
    rule_set_slug = request.args.get('rule_set', '').strip()
    auto_start_param = (request.args.get('auto_start') or '').strip().lower()
    auto_start = auto_start_param in ('1', 'true', 'yes', 'on')
    if rule_set_slug:
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
        if rule_set:
            user = getattr(g, 'current_user', None)
            is_owner = bool(user and rule_set.created_by_user_id == user.id)
            if getattr(rule_set, 'visibility_status', 'public') != 'public' and not is_owner:
                return redirect(url_for('play_quiz'))
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

    # Récupérer les sets de règles visibles
    user = getattr(g, 'current_user', None)
    if user:
        rule_sets = QuizRuleSet.query.filter(
            QuizRuleSet.is_active.is_(True),
            db.or_(
                QuizRuleSet.visibility_status == 'public',
                QuizRuleSet.created_by_user_id == user.id
            )
        ).order_by(QuizRuleSet.name).all()
    else:
        rule_sets = QuizRuleSet.query.filter_by(is_active=True, visibility_status='public').order_by(QuizRuleSet.name).all()

    quick_double_click_pref = _get_user_double_click_preference()
    if 'quick_double_click_enabled' in session:
        quick_double_click_enabled = bool(session.get('quick_double_click_enabled'))
    else:
        quick_double_click_enabled = quick_double_click_pref
        session['quick_double_click_enabled'] = quick_double_click_enabled

    rule_set_stats = None
    if rule_set:
        user_id = g.current_user.id if getattr(g, 'current_user', None) and g.current_user.is_authenticated else None
        rule_set_stats = get_rule_set_stats(rule_set, user_id)

    return render_template('play.html',
                           rule_sets=rule_sets,
                           rule_set=rule_set,
                           rule_set_stats=rule_set_stats,
                           quick_double_click=quick_double_click_enabled,
                           auto_start=auto_start)


def play_quiz_by_slug(slug):
    """
    Page pour jouer à un quiz spécifique via son slug.
    Route propre pour partage sur réseaux sociaux: /play/<slug>
    """
    rule_set = QuizRuleSet.query.filter_by(slug=slug, is_active=True).first()

    if not rule_set:
        # Redirection vers la page de sélection si le slug n'existe pas
        return redirect(url_for('play_quiz'))

    user = getattr(g, 'current_user', None)
    is_owner = bool(user and rule_set.created_by_user_id == user.id)
    if getattr(rule_set, 'visibility_status', 'public') != 'public' and not is_owner:
        return redirect(url_for('play_quiz'))

    # Récupérer tous les sets de règles actifs pour le sélecteur
    if user:
        rule_sets = QuizRuleSet.query.filter(
            QuizRuleSet.is_active.is_(True),
            db.or_(
                QuizRuleSet.visibility_status == 'public',
                QuizRuleSet.created_by_user_id == user.id
            )
        ).order_by(QuizRuleSet.name).all()
    else:
        rule_sets = QuizRuleSet.query.filter_by(is_active=True, visibility_status='public').order_by(QuizRuleSet.name).all()

    quick_double_click_pref = _get_user_double_click_preference()
    if 'quick_double_click_enabled' in session:
        quick_double_click_enabled = bool(session.get('quick_double_click_enabled'))
    else:
        quick_double_click_enabled = quick_double_click_pref
        session['quick_double_click_enabled'] = quick_double_click_enabled

    # Auto-démarrage activé par défaut pour cette route
    auto_start = True

    user_id = g.current_user.id if getattr(g, 'current_user', None) and g.current_user.is_authenticated else None
    rule_set_stats = get_rule_set_stats(rule_set, user_id)

    return render_template('play.html',
                           rule_sets=rule_sets,
                           rule_set=rule_set,
                           rule_set_stats=rule_set_stats,
                           quick_double_click=quick_double_click_enabled,
                           auto_start=auto_start)
