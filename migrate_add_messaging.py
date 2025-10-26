"""
Migration: création des tables de messagerie interne

Tables:
- conversations
- conversation_participants
- conversation_messages
"""

from app import app, db
from sqlalchemy import text


def migrate():
    with app.app_context():
        print("[MIGRATION] Début migration messagerie interne...")
        try:
            # Conversations
            db.session.execute(text(
                """
                CREATE TABLE IF NOT EXISTS conversations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    subject TEXT,
                    context_type VARCHAR(50),
                    context_id INTEGER
                )
                """
            ))

            # Participants
            db.session.execute(text(
                """
                CREATE TABLE IF NOT EXISTS conversation_participants (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    conversation_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    last_read_at DATETIME,
                    UNIQUE(conversation_id, user_id),
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """
            ))

            # Messages
            db.session.execute(text(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    conversation_id INTEGER NOT NULL,
                    sender_id INTEGER NOT NULL,
                    content TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id),
                    FOREIGN KEY(sender_id) REFERENCES users(id)
                )
                """
            ))

            db.session.commit()
            print("[OK] Tables de messagerie prêtes")
        except Exception as e:
            db.session.rollback()
            print(f"[ERREUR] Migration messagerie: {e}")
            raise


if __name__ == '__main__':
    migrate()


