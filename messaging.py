from flask import render_template, request, redirect, url_for, flash, g
from models import db, ConversationParticipant, Conversation, ConversationMessage, QuestionReport, ContactMessage, User, Question, QuizRuleSet, Profile
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
        print(f"[NOTIFY] Début notification pour conversation {conv_id}, expéditeur: {user.username}")
        other_parts = ConversationParticipant.query.filter(ConversationParticipant.conversation_id == conv_id, ConversationParticipant.user_id != user.id).all()
        print(f"[NOTIFY] {len(other_parts)} autres participants trouvés")
        if other_parts:
            recipients = User.query.filter(User.id.in_([p.user_id for p in other_parts])).all()
            conv = Conversation.query.get(conv_id)
            print(f"[NOTIFY] Conversation sujet: {conv.subject if conv else 'N/A'}")
            for r in recipients:
                print(f"[NOTIFY] Vérification destinataire: {r.username} (id={r.id})")
                prefs = r.get_preferences()
                has_email = bool(r.email)
                notify_enabled = prefs.get('notify_email_on_message', False)
                print(f"[NOTIFY]   - Email: {r.email if has_email else 'AUCUN'}")
                print(f"[NOTIFY]   - Notification activée: {notify_enabled}")
                print(f"[NOTIFY]   - Préférences complètes: {prefs}")
                if notify_enabled and has_email:
                    try:
                        print(f"[NOTIFY] Envoi email à {r.email}")
                        send_email_optional(
                            to_email=r.email,
                            subject=f"Nouveau message: {conv.subject or 'Conversation'}",
                            body=f"{user.username} a envoyé un nouveau message.\n\n{content}\n\nAccéder à la conversation: {request.host_url.rstrip('/')}/messages"
                        )
                        print(f"[NOTIFY] Email envoyé avec succès à {r.email}")
                    except Exception as e:
                        print(f"[NOTIFY] ERREUR envoi email à {r.email}: {e}")
                else:
                    print(f"[NOTIFY] Email NON envoyé à {r.username}: notification={notify_enabled}, email={has_email}")

        # Réafficher le fil
        messages = ConversationMessage.query.filter_by(conversation_id=conv_id).order_by(ConversationMessage.created_at.asc()).all()
        conv = Conversation.query.get(conv_id)
        return render_template('partials/conversation_thread.html', conversation=conv, messages=messages, me=user)
    except Exception as e:
        db.session.rollback()
        return f"<div class='alert alert-danger'>Erreur lors de l'envoi: {str(e)}</div>", 200


def contact_page():
    print(f"[CONTACT] Method: {request.method}")
    if request.method == 'POST':
        name = (request.form.get('name') or '').strip()
        email = (request.form.get('email') or '').strip()
        message = (request.form.get('message') or '').strip()
        print(f"[CONTACT] Received: name='{name}', email='{email}', message='{message[:50]}...'")

        if not name or not email or not message:
            print(f"[CONTACT] Validation failed: name={bool(name)}, email={bool(email)}, message={bool(message)}")
            flash('Tous les champs sont requis.', 'danger')
            return render_template('contact.html')

        try:
            print("[CONTACT] Creating ContactMessage...")
            # Créer le message de contact
            contact_msg = ContactMessage(
                visitor_name=name,
                visitor_email=email,
                message=message
            )
            db.session.add(contact_msg)
            db.session.flush()
            print(f"[CONTACT] ContactMessage created with id={contact_msg.id}")

            # Trouver les administrateurs (utilisateurs avec profil "Administrateur")
            print("[CONTACT] Looking for admin profile...")
            admin_profile = Profile.query.filter_by(name='Administrateur').first()
            admin_users = []
            if admin_profile:
                print(f"[CONTACT] Found admin profile id={admin_profile.id}")
                admin_users = User.query.filter_by(profile_id=admin_profile.id, is_active=True).all()
                print(f"[CONTACT] Found {len(admin_users)} active admin users: {[u.username for u in admin_users]}")
            else:
                print("[CONTACT] No admin profile found!")

            # Créer une conversation si il y a des admins
            if admin_users:
                print("[CONTACT] Creating conversation...")
                subject = f"Contact: Message de {name}"
                conv = Conversation(subject=subject, context_type='contact_message', context_id=contact_msg.id)
                db.session.add(conv)
                db.session.flush()
                print(f"[CONTACT] Conversation created with id={conv.id}")

                # Ajouter les participants (admins)
                for admin in admin_users:
                    print(f"[CONTACT] Adding participant: {admin.username} (id={admin.id})")
                    db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=admin.id, last_read_at=None))

                # Message initial
                content = f"Message de contact de {name} ({email}):\n\n{message}"
                print("[CONTACT] Creating initial message...")
                msg = ConversationMessage(conversation_id=conv.id, sender_id=None, content=content)  # sender_id=None pour les messages système
                db.session.add(msg)

                # Lier la conversation au message de contact
                contact_msg.conversation_id = conv.id

                # Envoyer emails aux admins ayant activé les notifications
                print(f"[CONTACT] Début envoi emails aux {len(admin_users)} admins")
                for admin in admin_users:
                    prefs = admin.get_preferences()
                    notify = prefs.get('notify_email_on_message', False)
                    has_email = bool(admin.email)
                    print(f"[CONTACT] Admin {admin.username} (id={admin.id}): notify={notify}, has_email={has_email}")
                    print(f"[CONTACT]   - Email: {admin.email if has_email else 'AUCUN'}")
                    print(f"[CONTACT]   - Préférences complètes: {prefs}")
                    if notify and has_email:
                        try:
                            print(f"[CONTACT] Envoi email de contact à {admin.email}")
                            send_email_optional(
                                to_email=admin.email,
                                subject=f"Nouveau message de contact: {subject}",
                                body=f"Un nouveau message de contact a été reçu de {name}.\n\n{message}\n\nAccéder à la conversation: {request.host_url.rstrip('/')}/messages"
                            )
                            print(f"[CONTACT] Email envoyé avec succès à {admin.email}")
                        except Exception as e:
                            print(f"[CONTACT] ERREUR envoi email à {admin.email}: {e}")
                    else:
                        print(f"[CONTACT] Email NON envoyé à {admin.username}: notification={notify}, email={has_email}")

            print("[CONTACT] Committing transaction...")
            db.session.commit()
            print("[CONTACT] Transaction committed successfully")
            flash('Merci, votre message a été envoyé.', 'success')
            return redirect(url_for('contact_page'))

        except Exception as e:
            db.session.rollback()
            print(f"[CONTACT] Error during contact message creation: {e}")
            import traceback
            traceback.print_exc()
            flash('Une erreur est survenue lors de l\'envoi de votre message.', 'danger')
            return render_template('contact.html')

    return render_template('contact.html')


def report_form():
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return "<div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-warning'>Vous devez être connecté avec un compte protégé par mot de passe pour signaler un problème.</div></div>", 200

    qid = (request.args.get('question_id') or '').strip()
    if not qid.isdigit():
        return "<div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Identifiant de question invalide.</div></div>", 200

    question = Question.query.get(int(qid))
    if not question:
        return "<div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Question introuvable.</div></div>", 200

    rule_set_slug = (request.args.get('rule_set') or '').strip()
    rule_set = None
    if rule_set_slug:
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

    author_user = question.author_user
    rule_creator = rule_set.created_by_user if rule_set else None

    inner = render_template('report_form.html', question=question, rule_set=rule_set, author_user=author_user, rule_creator=rule_creator)
    # Remplacer entièrement le conteneur pour l'afficher
    return f"<div id='modal-root' class='modal-overlay' style='display:flex'>{inner}</div>"


def report_submit():
    user = getattr(g, 'current_user', None)
    if not user or not user.password_hash:
        return "<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-warning'>Vous devez être connecté avec un compte protégé par mot de passe.</div></div></div>", 200

    qid = (request.form.get('question_id') or '').strip()
    reason = (request.form.get('reason') or '').strip()
    details = (request.form.get('details') or '').strip()
    rule_set_slug = (request.form.get('rule_set') or '').strip()

    if not qid.isdigit():
        return "<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Identifiant de question invalide.</div></div></div>", 200
    if not reason or not details:
        return "<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Merci de préciser la raison et les détails.</div></div></div>", 200

    question = Question.query.get(int(qid))
    if not question:
        return "<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Question introuvable.</div></div></div>", 200

    rule_set = None
    if rule_set_slug:
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

    # Déterminer les destinataires
    to_author = (request.form.get('to_author') == '1')
    to_rule_creator = (request.form.get('to_rule_creator') == '1')
    to_admins = (request.form.get('to_admins') == '1')

    recipient_ids = set()
    if to_author and question.author_id:
        recipient_ids.add(int(question.author_id))
    if to_rule_creator and rule_set and rule_set.created_by_user_id:
        recipient_ids.add(int(rule_set.created_by_user_id))
    if to_admins:
        for adm in User.query.filter_by(is_admin=True, is_active=True).all():
            recipient_ids.add(adm.id)

    # Exclure l'expéditeur
    if user.id in recipient_ids:
        recipient_ids.remove(user.id)

    try:
        # Créer la conversation
        subject = f"Signalement Q{question.id}: {question.question_text[:60]}"
        conv = Conversation(subject=subject, context_type='question_report', context_id=None)
        db.session.add(conv)
        db.session.flush()

        # Participants: reporter + destinataires
        db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=user.id, last_read_at=datetime.utcnow()))
        for rid in recipient_ids:
            db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=rid, last_read_at=None))

        # Message initial
        content = f"Raison: {reason}\n\n{details}"
        msg = ConversationMessage(conversation_id=conv.id, sender_id=user.id, content=content)
        db.session.add(msg)
        db.session.flush()

        # Créer le report et relier la conversation
        report = QuestionReport(
            question_id=question.id,
            rule_set_id=(rule_set.id if rule_set else None),
            reporter_id=user.id,
            reason=reason,
            details=details,
            status='open',
            conversation_id=conv.id,
        )
        db.session.add(report)
        conv.context_id = report.id

        db.session.commit()

        # Envoi emails (optionnel)
        print(f"[REPORT] Début envoi emails pour signalement, {len(recipient_ids)} destinataires")
        # Récupérer préférences des destinataires
        if recipient_ids:
            recips = User.query.filter(User.id.in_(list(recipient_ids))).all()
            print(f"[REPORT] {len(recips)} utilisateurs destinataires trouvés")
            for r in recips:
                print(f"[REPORT] Vérification destinataire: {r.username} (id={r.id})")
                prefs = r.get_preferences()
                has_email = bool(r.email)
                notify_enabled = prefs.get('notify_email_on_message', False)
                print(f"[REPORT]   - Email: {r.email if has_email else 'AUCUN'}")
                print(f"[REPORT]   - Notification activée: {notify_enabled}")
                print(f"[REPORT]   - Préférences complètes: {prefs}")
                if notify_enabled and has_email:
                    try:
                        print(f"[REPORT] Envoi email de signalement à {r.email}")
                        send_email_optional(
                            to_email=r.email,
                            subject=f"Nouveau message: {subject}",
                            body=f"Un nouveau signalement a été créé par {user.username}.\n\n{details}\n\nAccéder à la conversation: {request.host_url.rstrip('/')}/messages"
                        )
                        print(f"[REPORT] Email envoyé avec succès à {r.email}")
                    except Exception as e:
                        print(f"[REPORT] ERREUR envoi email à {r.email}: {e}")
                else:
                    print(f"[REPORT] Email NON envoyé à {r.username}: notification={notify_enabled}, email={has_email}")

        html = (
            "<div id='modal-root' class='modal-overlay' style='display:flex'>"
            "<div class='modal-content' style='padding:1.5rem'>"
            "<h3>Merci pour votre signalement</h3>"
            "<p>Votre message a été envoyé aux destinataires sélectionnés.</p>"
            "<div style='display:flex; gap:.5rem; justify-content:flex-end'>"
            "<a class='btn btn-primary' href='/messages'>Ouvrir la messagerie</a>"
            "<button class='btn btn-secondary' onclick=\"document.getElementById('modal-root').style.display='none'\">Fermer</button>"
            "</div>"
            "</div>"
            "</div>"
        )
        return html
    except Exception as e:
        db.session.rollback()
        return f"<div id='modal-root' class='modal-overlay' style='display:flex'><div class='modal-content'><div class='modal-header'><h3>Signaler un problème</h3></div><div class='alert alert-danger'>Erreur lors de l'envoi: {str(e)}</div></div></div>", 200
