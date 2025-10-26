"""
Migration: création de la table question_reports

Champs:
- id
- created_at, updated_at
- question_id (FK questions.id)
- rule_set_id (FK quiz_rule_sets.id, nullable)
- reporter_id (FK users.id)
- reason (str)
- details (text)
- status (open|closed)
- conversation_id (FK conversations.id, nullable)
"""

from app import app, db
from sqlalchemy import text


def migrate():
    with app.app_context():
        print("[MIGRATION] Début migration question_reports...")
        try:
            db.session.execute(text(
                """
                CREATE TABLE IF NOT EXISTS question_reports (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    question_id INTEGER NOT NULL,
                    rule_set_id INTEGER,
                    reporter_id INTEGER NOT NULL,
                    reason VARCHAR(100) NOT NULL,
                    details TEXT NOT NULL,
                    status VARCHAR(20) NOT NULL DEFAULT 'open',
                    conversation_id INTEGER,
                    FOREIGN KEY(question_id) REFERENCES questions(id),
                    FOREIGN KEY(rule_set_id) REFERENCES quiz_rule_sets(id),
                    FOREIGN KEY(reporter_id) REFERENCES users(id),
                    FOREIGN KEY(conversation_id) REFERENCES conversations(id)
                )
                """
            ))

            db.session.commit()
            print("[OK] Table question_reports prête")
        except Exception as e:
            db.session.rollback()
            print(f"[ERREUR] Migration question_reports: {e}")
            raise


if __name__ == '__main__':
    migrate()


