from flask import render_template, request, redirect, url_for, flash, g
from models import db, ConversationParticipant, Conversation, ConversationMessage, QuestionReport, ContactMessage, User
from sqlalchemy import or_
from datetime import datetime
from email_utils import send_email_optional


def messages_home():
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return redirect(url_for('play_quiz'))
    return render_template('messages.html')


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
