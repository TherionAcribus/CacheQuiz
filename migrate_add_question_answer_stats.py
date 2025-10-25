"""
Migration: création de la table question_answer_stats pour suivre la répartition des réponses

Champs:
- id
- created_at, updated_at
- question_id (FK questions.id)
- answer_index (1..n)
- selected_count (compteur)
Contraintes: (question_id, answer_index) unique
"""

from app import app, db
from sqlalchemy import text


def migrate():
    with app.app_context():
        print("[MIGRATION] Début migration question_answer_stats...")
        try:
            db.session.execute(text(
                """
                CREATE TABLE IF NOT EXISTS question_answer_stats (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL,
                    question_id INTEGER NOT NULL,
                    answer_index INTEGER NOT NULL,
                    selected_count INTEGER NOT NULL DEFAULT 0,
                    CONSTRAINT uq_question_answer_index_stat UNIQUE (question_id, answer_index),
                    FOREIGN KEY(question_id) REFERENCES questions(id)
                )
                """
            ))
            db.session.commit()
            print("[OK] Table question_answer_stats prête")
        except Exception as e:
            db.session.rollback()
            print(f"[ERREUR] Migration question_answer_stats: {e}")
            raise


if __name__ == '__main__':
    migrate()


