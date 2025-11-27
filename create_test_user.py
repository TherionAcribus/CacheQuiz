from app import app
from models import db, User

with app.app_context():
    # Créer un utilisateur de test pour les messages
    test_user = User(username='testuser', email='test@example.com', is_active=True)
    db.session.add(test_user)
    db.session.commit()
    print(f"Utilisateur de test créé: {test_user.username} (id: {test_user.id})")

    # Créer une conversation de test
    from models import Conversation, ConversationParticipant, ConversationMessage
    conv = Conversation(subject='Conversation de test', context_type=None, context_id=None)
    db.session.add(conv)
    db.session.commit()

    # Ajouter l'utilisateur comme participant
    part = ConversationParticipant(conversation_id=conv.id, user_id=test_user.id, last_read_at=None)
    db.session.add(part)

    # Ajouter un message système
    msg = ConversationMessage(conversation_id=conv.id, sender_id=None, content="Ceci est une conversation de test pour vérifier la modale de suppression.")
    db.session.add(msg)

    db.session.commit()
    print(f"Conversation de test créée (id: {conv.id})")
