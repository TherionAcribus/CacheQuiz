from datetime import datetime
from flask import render_template, request, g

from models import (
    db,
    Question,
    QuizRuleSet,
    Conversation,
    ConversationParticipant,
    ConversationMessage,
)
from auth import _ensure_admin_page_redirect, _ensure_perm_api, _has_perm, _deny_access


def admin_validation_page():
    """Page admin: validation des contenus (questions + quiz)."""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_manage_profiles'):
        return _deny_access("Permission 'can_manage_profiles' requise")
    return render_template('admin_validation.html')


def list_pending_questions():
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied
    qs = Question.query.filter(
        Question.is_published.is_(False),
        Question.is_private.is_(False),
    ).order_by(Question.updated_at.desc()).all()
    return render_template('admin_validation_questions_list.html', questions=qs)


def list_pending_quiz_rules():
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied
    rules = QuizRuleSet.query.filter(
        QuizRuleSet.visibility_status == 'pending',
        QuizRuleSet.is_active.is_(True),
    ).order_by(QuizRuleSet.updated_at.desc()).all()
    return render_template('admin_validation_quiz_rules_list.html', rules=rules)


def _get_or_create_question_publication_conversation(question: Question):
    conv = Conversation.query.filter_by(context_type='question_publication', context_id=question.id).order_by(Conversation.created_at.desc()).first()
    if conv:
        return conv
    subject = f"Validation question Q{question.id}: {question.question_text[:60]}"
    conv = Conversation(subject=subject, context_type='question_publication', context_id=question.id)
    db.session.add(conv)
    db.session.flush()
    return conv


def _get_or_create_quiz_publication_conversation(rule: QuizRuleSet):
    conv = Conversation.query.filter_by(context_type='quiz_publication', context_id=rule.id).order_by(Conversation.created_at.desc()).first()
    if conv:
        return conv
    subject = f"Publication quiz: {rule.name} ({rule.slug})"
    conv = Conversation(subject=subject, context_type='quiz_publication', context_id=rule.id)
    db.session.add(conv)
    db.session.flush()
    return conv


def _get_hx_prompt_text() -> str | None:
    """HTMX hx-prompt envoie la valeur dans l'en-tête HX-Prompt (pas forcément dans request.form)."""
    raw = (request.form.get('prompt') or request.form.get('note') or request.headers.get('HX-Prompt') or '').strip()
    return raw or None


def confirm_approve_question_validation(question_id: int):
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied
    q = Question.query.get_or_404(question_id)
    inner = render_template(
        'admin_confirm_modal.html',
        title="Valider la question",
        message="Vous pouvez ajouter un message optionnel qui sera envoyé au créateur dans la messagerie.",
        action_url=f"/api/admin/validation/question/{q.id}/approve",
        target_selector="#pending-questions",
        confirm_label="✅ Publier",
        show_note=True,
        note_placeholder="Ex: Merci ! Petite remarque: ...",
    )
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"


def confirm_reject_question_validation(question_id: int):
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied
    q = Question.query.get_or_404(question_id)
    inner = render_template(
        'admin_confirm_modal.html',
        title="Refuser la question",
        message="Ajoutez une raison (recommandé) qui sera envoyée au créateur dans la messagerie.",
        action_url=f"/api/admin/validation/question/{q.id}/reject",
        target_selector="#pending-questions",
        confirm_label="❌ Refuser",
        show_note=True,
        note_placeholder="Ex: La source est manquante / La réponse semble incorrecte / ...",
    )
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"


def confirm_approve_quiz_rule_validation(rule_id: int):
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied
    rule = QuizRuleSet.query.get_or_404(rule_id)
    inner = render_template(
        'admin_confirm_modal.html',
        title="Valider la publication du quiz",
        message="Vous pouvez ajouter un message optionnel qui sera envoyé au créateur dans la messagerie.",
        action_url=f"/api/admin/validation/quiz-rule/{rule.id}/approve",
        target_selector="#pending-quiz-rules",
        confirm_label="✅ Publier",
        show_note=True,
        note_placeholder="Ex: Merci ! Petite remarque: ...",
    )
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"


def confirm_reject_quiz_rule_validation(rule_id: int):
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied
    rule = QuizRuleSet.query.get_or_404(rule_id)
    inner = render_template(
        'admin_confirm_modal.html',
        title="Refuser la publication du quiz",
        message="Ajoutez une raison (optionnel) qui sera envoyée au créateur dans la messagerie.",
        action_url=f"/api/admin/validation/quiz-rule/{rule.id}/reject",
        target_selector="#pending-quiz-rules",
        confirm_label="❌ Refuser",
        show_note=True,
        note_placeholder="Ex: Quiz trop vague / contenu douteux / règles incohérentes / ...",
    )
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"


def approve_quiz_rule_validation(rule_id: int):
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied

    rule = QuizRuleSet.query.get_or_404(rule_id)
    admin = getattr(g, 'current_user', None)
    note = _get_hx_prompt_text()

    try:
        rule.visibility_status = 'public'
        rule.public_reviewed_at = datetime.utcnow()
        rule.public_reviewed_by_user_id = admin.id if admin else None
        rule.public_review_note = note
        rule.updated_at = datetime.utcnow()

        conv = _get_or_create_quiz_publication_conversation(rule)

        if rule.created_by_user_id:
            existing = ConversationParticipant.query.filter_by(conversation_id=conv.id, user_id=rule.created_by_user_id).first()
            if not existing:
                db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=rule.created_by_user_id, last_read_at=None))

        msg = f"✅ Publication approuvée. Votre quiz « {rule.name} » est maintenant PUBLIC."
        if note:
            msg += f"\n\nMessage de l'équipe:\n{note}"

        db.session.add(ConversationMessage(
            conversation_id=conv.id,
            sender_id=admin.id if admin else None,
            content=msg,
        ))

        db.session.commit()
        return list_pending_quiz_rules()
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def reject_quiz_rule_validation(rule_id: int):
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied

    rule = QuizRuleSet.query.get_or_404(rule_id)
    admin = getattr(g, 'current_user', None)
    note = _get_hx_prompt_text()

    try:
        rule.visibility_status = 'rejected'
        rule.public_reviewed_at = datetime.utcnow()
        rule.public_reviewed_by_user_id = admin.id if admin else None
        rule.public_review_note = note
        rule.updated_at = datetime.utcnow()

        conv = _get_or_create_quiz_publication_conversation(rule)

        if rule.created_by_user_id:
            existing = ConversationParticipant.query.filter_by(conversation_id=conv.id, user_id=rule.created_by_user_id).first()
            if not existing:
                db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=rule.created_by_user_id, last_read_at=None))

        msg = f"❌ Publication refusée pour « {rule.name} »."
        if note:
            msg += f"\n\nRaison: {note}"

        db.session.add(ConversationMessage(
            conversation_id=conv.id,
            sender_id=admin.id if admin else None,
            content=msg,
        ))

        db.session.commit()
        return list_pending_quiz_rules()
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def approve_question_validation(question_id: int):
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied

    q = Question.query.get_or_404(question_id)
    admin = getattr(g, 'current_user', None)
    note = _get_hx_prompt_text()

    try:
        q.is_private = False
        q.is_published = True
        q.updated_at = datetime.utcnow()

        conv = _get_or_create_question_publication_conversation(q)
        # s'assurer que l'auteur est participant
        if q.author_id:
            existing = ConversationParticipant.query.filter_by(conversation_id=conv.id, user_id=q.author_id).first()
            if not existing:
                db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=q.author_id, last_read_at=None))

        msg = f"✅ Question validée et publiée (Q{q.id}). Merci pour votre contribution !"
        if note:
            msg += f"\n\nMessage de l'équipe:\n{note}"

        db.session.add(ConversationMessage(
            conversation_id=conv.id,
            sender_id=admin.id if admin else None,
            content=msg,
        ))

        db.session.commit()

        return list_pending_questions()
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


def reject_question_validation(question_id: int):
    denied = _ensure_perm_api('can_manage_profiles')
    if denied:
        return denied

    q = Question.query.get_or_404(question_id)
    admin = getattr(g, 'current_user', None)
    note = _get_hx_prompt_text()

    try:
        q.is_published = False
        q.is_private = True  # retour en privé, le créateur pourra redemander
        q.updated_at = datetime.utcnow()

        conv = _get_or_create_question_publication_conversation(q)
        if q.author_id:
            existing = ConversationParticipant.query.filter_by(conversation_id=conv.id, user_id=q.author_id).first()
            if not existing:
                db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=q.author_id, last_read_at=None))

        msg = f"❌ Validation refusée pour la question Q{q.id}."
        if note:
            msg += f"\n\nRaison: {note}"

        db.session.add(ConversationMessage(
            conversation_id=conv.id,
            sender_id=admin.id if admin else None,
            content=msg,
        ))

        db.session.commit()

        return list_pending_questions()
    except Exception as e:
        db.session.rollback()
        return f"Erreur: {str(e)}", 400


