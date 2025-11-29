from flask import render_template, request, redirect, url_for, flash, g, session, current_app
from models import db, User, SavedQuestion, Question, UserQuestionStat, BroadTheme, SpecificTheme, UserQuizSession
from werkzeug.security import generate_password_hash
from itsdangerous import URLSafeTimedSerializer, SignatureExpired, BadSignature
from sqlalchemy import func
import re
from email_utils import send_email_optional


def _get_token_serializer():
    """Retourne le serializer pour les tokens de reset de mot de passe."""
    return URLSafeTimedSerializer(current_app.config['SECRET_KEY'])


def send_reset_email_logic(user):
    """Logique métier pour envoyer l'email de réinitialisation."""
    if not user or not user.email:
        return False
        
    s = _get_token_serializer()
    token = s.dumps({'uid': user.id})
    reset_link = url_for('reset_password', token=token, _external=True)
    
    subject = "Réinitialisation de votre mot de passe - CacheQuiz"
    body = f"""Bonjour {user.username},

Vous avez demandé la réinitialisation de votre mot de passe.
Cliquez sur le lien suivant pour choisir un nouveau mot de passe :

{reset_link}

Ce lien est valide pour 1 heure.
Si vous n'êtes pas à l'origine de cette demande, ignorez cet email.

L'équipe CacheQuiz
"""
    send_email_optional(user.email, subject, body)
    return True


def forgot_password():
    if request.method == 'POST':
        email = (request.form.get('email') or '').strip()
        if not email:
            return render_template('forgot_password.html', error="Email requis")
        user = User.query.filter_by(email=email).first()
        # Toujours indiquer que l'email a été envoyé pour éviter la fuite d'existence
        if user:
            send_reset_email_logic(user)
            return render_template('forgot_password.html', info="Un email a été envoyé.")
        return render_template('forgot_password.html', info="Un email a été envoyé.")
    return render_template('forgot_password.html')


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


def check_question_saved(question_id: int):
    """Vérifier si une question est sauvegardée par l'utilisateur connecté."""
    if not g.current_user:
        return {'is_saved': False}

    existing = SavedQuestion.query.filter_by(
        user_id=g.current_user.id,
        question_id=question_id
    ).first()

    return {'is_saved': existing is not None}


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
