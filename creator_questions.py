from datetime import datetime
from flask import render_template, request, g, redirect, url_for

from models import (
    db,
    Question,
    BroadTheme,
    SpecificTheme,
    Country,
    ImageAsset,
    AnswerImageLink,
    Keyword,
    QuestionAnswerStat,
    UserQuestionStat,
    SavedQuestion,
    Conversation,
    ConversationParticipant,
    ConversationMessage,
    Profile,
    User,
)
from auth import _ensure_creator_page_redirect, _ensure_creator_api
from email_utils import send_email_optional


def creator_questions_page():
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp
    return render_template('creator_questions.html')


def list_creator_questions():
    denied = _ensure_creator_api()
    if denied:
        return denied

    user = g.current_user
    questions = Question.query.filter_by(author_id=user.id).order_by(Question.updated_at.desc()).all()
    return render_template('creator_questions_list.html', questions=questions, me=user)


def creator_new_question():
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp

    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
    return render_template(
        'question_form.html',
        question=None,
        themes=themes,
        specific_themes=specific_themes,
        countries=countries,
        images=images,
        creator_mode=True,
        form_action='/api/creator/question',
    )


def creator_edit_question(question_id: int):
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp

    q = Question.query.get_or_404(question_id)
    user = g.current_user
    if not user or q.author_id != user.id:
        return redirect(url_for('creator_access_denied_page'))

    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
    return render_template(
        'question_form.html',
        question=q,
        themes=themes,
        specific_themes=specific_themes,
        countries=countries,
        images=images,
        creator_mode=True,
        form_action=f'/api/creator/question/{q.id}',
    )


def _parse_answers_and_links(data):
    possible_answers = []
    answer_images_per_answer = []
    links_to_add = []
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
    return possible_answers, answer_images_per_answer, links_to_add


def create_creator_question():
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied

        data = request.form
        user = g.current_user

        broad_theme_raw = (data.get('broad_theme_id') or '').strip()
        if not broad_theme_raw.isdigit():
            return "Thématique large obligatoire", 400

        possible_answers, answer_images_per_answer, links_to_add = _parse_answers_and_links(data)

        q = Question(
            author_id=user.id,
            question_text=(data.get('question_text') or '').strip(),
            possible_answers='|||'.join(possible_answers),
            answer_images='|||'.join(answer_images_per_answer),
            correct_answer=(data.get('correct_answer') or '').strip(),
            detailed_answer=(data.get('detailed_answer') or '').strip() or None,
            hint=(data.get('hint') or '').strip() or None,
            source=(data.get('source') or '').strip() or None,
            detailed_answer_image_id=int(data.get('detailed_answer_image_id')) if (data.get('detailed_answer_image_id') or '').isdigit() else None,
            broad_theme_id=int(broad_theme_raw),
            specific_theme_id=int(data.get('specific_theme_id')) if (data.get('specific_theme_id') or '').isdigit() else None,
            difficulty_level=int(data.get('difficulty_level', 1)),
            translation_id=int(data.get('translation_id')) if (data.get('translation_id') or '').isdigit() else None,
            is_published=False,  # Jamais publié directement côté créateur
            is_private=True,  # Privée par défaut (publication via demande explicite)
            publication_status='private',
            publication_requested_at=None,
            publication_reviewed_at=None,
            publication_review_note=None,
        )

        # Pays (many-to-many)
        country_ids = request.form.getlist('countries')
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            q.countries = countries

        # Image question (one selected via relation many-to-many)
        question_image_id = (request.form.get('question_image_id') or '').strip()
        if question_image_id.isdigit():
            img = ImageAsset.query.get(int(question_image_id))
            q.images = [img] if img else []
        else:
            q.images = []

        # Keywords (many-to-many)
        keyword_ids = request.form.getlist('keywords')
        if keyword_ids:
            keywords = Keyword.query.filter(Keyword.id.in_([int(kid) for kid in keyword_ids if (kid or '').isdigit()])).all()
            q.keywords = keywords

        db.session.add(q)
        db.session.flush()

        for answer_index, image_id in links_to_add:
            db.session.add(AnswerImageLink(question_id=q.id, answer_index=answer_index, image_id=image_id))

        db.session.commit()

        questions = Question.query.filter_by(author_id=user.id).order_by(Question.updated_at.desc()).all()
        return render_template('creator_questions_list.html', questions=questions, me=user)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def update_creator_question(question_id: int):
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied

        user = g.current_user
        q = Question.query.get_or_404(question_id)
        if q.author_id != user.id:
            return "Accès refusé", 403

        data = request.form

        broad_theme_raw = (data.get('broad_theme_id') or '').strip()
        if not broad_theme_raw.isdigit():
            return "Thématique large obligatoire", 400

        possible_answers, answer_images_per_answer, links_to_add = _parse_answers_and_links(data)

        q.question_text = (data.get('question_text') or '').strip()
        q.possible_answers = '|||'.join(possible_answers)
        q.answer_images = '|||'.join(answer_images_per_answer)
        q.correct_answer = (data.get('correct_answer') or '').strip()
        q.detailed_answer = (data.get('detailed_answer') or '').strip() or None
        q.hint = (data.get('hint') or '').strip() or None
        q.source = (data.get('source') or '').strip() or None
        q.detailed_answer_image_id = int(data.get('detailed_answer_image_id')) if (data.get('detailed_answer_image_id') or '').isdigit() else None
        q.broad_theme_id = int(broad_theme_raw)
        q.specific_theme_id = int(data.get('specific_theme_id')) if (data.get('specific_theme_id') or '').isdigit() else None
        q.difficulty_level = int(data.get('difficulty_level', 1))
        q.translation_id = int(data.get('translation_id')) if (data.get('translation_id') or '').isdigit() else None
        # Préserver l'état (privé vs en attente) : l'utilisateur demande explicitement la publication via l'action dédiée.
        # (On ne force pas is_private ici pour éviter de casser une demande déjà en cours.)
        q.is_published = False  # On ne publie pas via l'espace créateur
        q.updated_at = datetime.utcnow()

        # Pays
        country_ids = request.form.getlist('countries')
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            q.countries = countries
        else:
            q.countries = []

        # Image question
        question_image_id = (request.form.get('question_image_id') or '').strip()
        if question_image_id.isdigit():
            img = ImageAsset.query.get(int(question_image_id))
            q.images = [img] if img else []
        else:
            q.images = []

        # Keywords
        keyword_ids = request.form.getlist('keywords')
        if keyword_ids:
            keywords = Keyword.query.filter(Keyword.id.in_([int(kid) for kid in keyword_ids if (kid or '').isdigit()])).all()
            q.keywords = keywords
        else:
            q.keywords = []

        # Liens image->réponse
        AnswerImageLink.query.filter_by(question_id=q.id).delete()
        db.session.flush()
        for answer_index, image_id in links_to_add:
            db.session.add(AnswerImageLink(question_id=q.id, answer_index=answer_index, image_id=image_id))

        db.session.commit()

        questions = Question.query.filter_by(author_id=user.id).order_by(Question.updated_at.desc()).all()
        return render_template('creator_questions_list.html', questions=questions, me=user)
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def delete_creator_question(question_id: int):
    try:
        denied = _ensure_creator_api()
        if denied:
            return denied

        user = g.current_user
        q = Question.query.get_or_404(question_id)
        if q.author_id != user.id:
            return "Accès refusé", 403

        AnswerImageLink.query.filter_by(question_id=q.id).delete()
        QuestionAnswerStat.query.filter_by(question_id=q.id).delete()
        UserQuestionStat.query.filter_by(question_id=q.id).delete()
        SavedQuestion.query.filter_by(question_id=q.id).delete()

        q.countries = []
        q.keywords = []
        q.images = []

        db.session.delete(q)
        db.session.commit()

        questions = Question.query.filter_by(author_id=user.id).order_by(Question.updated_at.desc()).all()
        return render_template('creator_questions_list.html', questions=questions, me=user)
    except Exception as e:
        db.session.rollback()
        return f"Erreur lors de la suppression: {str(e)}", 400


def _get_admin_users():
    """Retourne la liste des utilisateurs admins (profil 'Administrateur')."""
    admin_profile = Profile.query.filter_by(name='Administrateur').first()
    if not admin_profile:
        return []
    return User.query.filter_by(profile_id=admin_profile.id, is_active=True).all()


def request_question_validation(question_id: int):
    """Le créateur autorise la question pour le pool (is_private=False) et notifie les admins."""
    denied = _ensure_creator_api()
    if denied:
        return denied

    user = g.current_user
    q = Question.query.get_or_404(question_id)
    if q.author_id != user.id:
        return "Accès refusé", 403

    # Autorisation de mise au pool: non privée, mais toujours non publiée tant qu'un admin n'a pas validé.
    q.is_private = False
    q.is_published = False
    q.publication_status = 'pending'
    q.publication_requested_at = datetime.utcnow()
    q.publication_reviewed_at = None
    q.publication_review_note = None
    q.updated_at = datetime.utcnow()

    try:
        subject = f"Validation question Q{q.id}: {q.question_text[:60]}"
        conv = Conversation(subject=subject, context_type='question_publication', context_id=q.id)
        db.session.add(conv)
        db.session.flush()

        # Participants: créateur + admins
        db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=user.id, last_read_at=datetime.utcnow()))
        admin_users = _get_admin_users()
        for adm in admin_users:
            db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=adm.id, last_read_at=None))

        content = (
            f"Demande de validation pour la question Q{q.id}.\n\n"
            f"Auteur: {user.username}\n"
            f"Thème large: {q.theme.name if q.theme else 'N/A'}\n\n"
            f"Question:\n{q.question_text}\n"
        )
        msg = ConversationMessage(conversation_id=conv.id, sender_id=user.id, content=content)
        db.session.add(msg)

        db.session.commit()

        # Emails optionnels selon préférences
        for adm in admin_users:
            prefs = adm.get_preferences()
            notify_enabled = prefs.get('notify_email_on_message', False)
            if notify_enabled and adm.email:
                try:
                    send_email_optional(
                        to_email=adm.email,
                        subject=f"Nouveau message: {subject}",
                        body=f"Une demande de validation a été envoyée par {user.username}.\n\nAccéder à la conversation: {request.host_url.rstrip('/')}/messages"
                    )
                except Exception:
                    pass

        questions = Question.query.filter_by(author_id=user.id).order_by(Question.updated_at.desc()).all()
        return render_template('creator_questions_list.html', questions=questions, me=user)
    except Exception as e:
        db.session.rollback()
        return f"Erreur lors de la demande de validation: {str(e)}", 400


def confirm_request_question_validation(question_id: int):
    """Retourne une modale de confirmation (cohérente avec le système de modales existant)."""
    denied = _ensure_creator_api()
    if denied:
        return denied

    user = g.current_user
    q = Question.query.get_or_404(question_id)
    if q.author_id != user.id:
        return "Accès refusé", 403

    inner = render_template(
        'creator_confirm_modal.html',
        title="Demander validation",
        message="Cette question restera invisible pour les autres tant qu’un administrateur ne l’aura pas validée.",
        action_url=f"/api/creator/question/{q.id}/request-validation",
        target_selector="#questions-list",
        confirm_label="✅ Envoyer la demande",
    )
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"


def creator_get_specific_themes_for_broad_theme():
    """Retourne les options HTML des sous-thèmes pour un thème large (mode créateur)."""
    denied = _ensure_creator_api()
    if denied:
        return denied
    broad_theme_id = (request.args.get('broad_theme_id') or '').strip()
    if broad_theme_id.isdigit():
        specific_themes = SpecificTheme.query.filter_by(broad_theme_id=int(broad_theme_id)).order_by(SpecificTheme.name).all()
    else:
        specific_themes = []
    return render_template('specific_theme_options.html', specific_themes=specific_themes)


