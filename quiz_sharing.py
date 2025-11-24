from flask import request, url_for, redirect, render_template, g
from models import db, QuizRuleSet, QuizShareLink
import uuid


def _parse_bool_param(value):
    """Convertit un paramètre en booléen fiable."""
    if isinstance(value, bool):
        return value
    if value is None:
        return False
    if isinstance(value, (int, float)):
        return bool(value)
    if isinstance(value, str):
        return value.strip().lower() in {"true", "1", "yes", "on"}
    return False


def create_quiz_share_link():
    """
    Crée un lien de partage personnalisé avec UUID pour les résultats du quiz.
    Retourne l'UUID et l'URL complète du lien de partage.
    """
    try:
        data = request.get_json() if request.is_json else request.form

        rule_set_slug = (data.get('rule_set') or '').strip()
        total_score = int(data.get('total_score', 0))
        total_correct_answers = int(data.get('total_correct_answers', 0))
        total_questions = int(data.get('total_questions', 0))
        success = _parse_bool_param(data.get('success'))
        perfect_bonus = _parse_bool_param(data.get('perfect_bonus'))
        combo_max = int(data.get('combo_max', 0))
        platform = (data.get('platform') or '').strip() or None

        if not rule_set_slug:
            return {'error': 'Quiz non spécifié'}, 400

        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
        if not rule_set:
            return {'error': 'Quiz introuvable'}, 404

        # Générer un UUID unique
        share_uuid = str(uuid.uuid4())

        # Créer le lien de partage
        share_link = QuizShareLink(
            uuid=share_uuid,
            user_id=g.current_user.id if getattr(g, 'current_user', None) else None,
            quiz_rule_set_id=rule_set.id,
            total_score=total_score,
            total_correct_answers=total_correct_answers,
            total_questions=total_questions,
            success=success,
            perfect_bonus_added=perfect_bonus,
            combo_max=combo_max,
            platform=platform
        )

        db.session.add(share_link)
        db.session.commit()

        # Retourner l'URL complète
        share_url = url_for('show_share_page', share_uuid=share_uuid, _external=True)

        return {
            'uuid': share_uuid,
            'url': share_url,
            'short_url': f'/share/{share_uuid}'
        }, 200

    except Exception as e:
        db.session.rollback()
        print(f"Erreur création lien de partage: {str(e)}")
        return {'error': f'Erreur serveur: {str(e)}'}, 500


def show_share_page(share_uuid):
    """
    Affiche la page de partage avec les résultats du quiz.
    Cette page contient les meta tags Open Graph optimisés pour le partage sur réseaux sociaux.
    """
    try:
        share_link = QuizShareLink.query.filter_by(uuid=share_uuid).first()

        if not share_link:
            return render_template('share_not_found.html'), 404

        # Vérifier l'expiration
        if share_link.is_expired():
            return render_template('share_expired.html', share_link=share_link), 410

        # Incrémenter le compteur de vues
        share_link.increment_view()
        db.session.commit()

        # Récupérer les informations du quiz
        rule_set = share_link.quiz_rule_set
        user = share_link.user

        return render_template(
            'share_page.html',
            share_link=share_link,
            rule_set=rule_set,
            user=user,
            total_score=share_link.total_score,
            total_correct_answers=share_link.total_correct_answers,
            total_questions=share_link.total_questions,
            success=share_link.success,
            perfect_bonus_added=share_link.perfect_bonus_added,
            combo_max=share_link.combo_max
        )

    except Exception as e:
        print(f"Erreur affichage page de partage: {str(e)}")
        return f"Erreur: {str(e)}", 500


def track_share_click(share_uuid):
    """
    Route pour tracker les clics sur le lien "Jouer au quiz" depuis la page de partage.
    Redirige vers le quiz après avoir incrémenté le compteur.
    """
    try:
        share_link = QuizShareLink.query.filter_by(uuid=share_uuid).first()

        if share_link and not share_link.is_expired():
            share_link.increment_click()
            db.session.commit()

            # Rediriger vers le quiz
            return redirect(url_for('play_quiz_by_slug', slug=share_link.quiz_rule_set.slug))
        else:
            return redirect(url_for('play_quiz'))

    except Exception as e:
        print(f"Erreur tracking clic partage: {str(e)}")
        return redirect(url_for('play_quiz'))
