"""
Migration: création de la table user_quiz_sessions pour suivre les sessions de quiz

Champs:
- id
- created_at, updated_at
- user_id (FK users.id)
- rule_set_id (FK quiz_rule_sets.id, nullable)
- status (in_progress|completed|abandoned)
- total_questions, answered_count, correct_count, total_score
"""

from app import app, db
from sqlalchemy import text


def migrate():
    with app.app_context():
        print("[MIGRATION] Début migration user_quiz_sessions...")
        try:
            # Créer la table si absente
            db.session.execute(text(
                """
                CREATE TABLE IF NOT EXISTS user_quiz_sessions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    user_id INTEGER NOT NULL,
                    rule_set_id INTEGER,
                    status VARCHAR(20) NOT NULL DEFAULT 'in_progress',
                    total_questions INTEGER NOT NULL DEFAULT 0,
                    answered_count INTEGER NOT NULL DEFAULT 0,
                    correct_count INTEGER NOT NULL DEFAULT 0,
                    total_score INTEGER NOT NULL DEFAULT 0,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(rule_set_id) REFERENCES quiz_rule_sets(id)
                )
                """
            ))
            db.session.commit()
            print("[OK] Table user_quiz_sessions prête")
        except Exception as e:
            db.session.rollback()
            print(f"[ERREUR] Migration user_quiz_sessions: {e}")
            raise


if __name__ == '__main__':
    migrate()


