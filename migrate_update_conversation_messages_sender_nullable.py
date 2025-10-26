"""
Migration: rendre sender_id nullable dans conversation_messages
pour supporter les messages système (ex: messages de contact)
"""

from app import app, db
from sqlalchemy import text


def migrate():
    with app.app_context():
        print("[MIGRATION] Début migration conversation_messages sender_id nullable...")
        try:
            # SQLite ne supporte pas ALTER COLUMN directement, il faut recréer la table
            db.session.execute(text(
                """
                CREATE TABLE IF NOT EXISTS conversation_messages_new (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    conversation_id INTEGER NOT NULL,
                    sender_id INTEGER,
                    content TEXT NOT NULL,
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id),
                    FOREIGN KEY(sender_id) REFERENCES users(id)
                )
                """
            ))

            # Copier les données
            db.session.execute(text(
                """
                INSERT INTO conversation_messages_new (id, created_at, updated_at, conversation_id, sender_id, content)
                SELECT id, created_at, updated_at, conversation_id, sender_id, content FROM conversation_messages
                """
            ))

            # Supprimer l'ancienne table et renommer la nouvelle
            db.session.execute(text("DROP TABLE conversation_messages"))
            db.session.execute(text("ALTER TABLE conversation_messages_new RENAME TO conversation_messages"))

            db.session.commit()
            print("[OK] conversation_messages.sender_id rendu nullable")
        except Exception as e:
            db.session.rollback()
            print(f"[ERREUR] Migration conversation_messages nullable: {e}")
            raise


if __name__ == '__main__':
    migrate()
