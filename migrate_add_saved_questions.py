from app import app, db
from sqlalchemy import text

print("🔄 Migration: Suppression et recréation de la table 'saved_questions'...")

with app.app_context():
    try:
        # Supprimer la table si elle existe
        db.session.execute(text('DROP TABLE IF EXISTS saved_questions'))
        db.session.commit()
        print("✓ Ancienne table supprimée")
        
        # Créer la table saved_questions avec TOUTES les colonnes
        db.session.execute(text('''
            CREATE TABLE saved_questions (
                id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                question_id INTEGER NOT NULL,
                created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
                notes TEXT,
                FOREIGN KEY (user_id) REFERENCES users(id),
                FOREIGN KEY (question_id) REFERENCES questions(id),
                CONSTRAINT uq_user_saved_question UNIQUE (user_id, question_id)
            )
        '''))
        db.session.commit()
        print("✅ Table 'saved_questions' créée avec succès avec toutes les colonnes")
    except Exception as e:
        db.session.rollback()
        print(f"❌ Erreur lors de la migration: {e}")
        raise
