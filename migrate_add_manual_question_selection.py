"""
Script de migration pour ajouter le mode de sélection manuelle de questions
aux QuizRuleSet.

Ce script ajoute :
1. Une nouvelle colonne 'question_selection_mode' (auto/manual)
2. Une nouvelle table d'association 'quiz_rule_set_questions' pour lier
   les règles aux questions spécifiques sélectionnées manuellement
"""

from app import app, db
from sqlalchemy import text

def migrate():
    with app.app_context():
        print("[MIGRATION] Debut de la migration pour la selection manuelle de questions...")
        
        try:
            # 1. Ajouter la colonne question_selection_mode à la table quiz_rule_sets
            print("[ETAPE 1] Ajout de la colonne 'question_selection_mode' a 'quiz_rule_sets'...")
            try:
                db.session.execute(text(
                    "ALTER TABLE quiz_rule_sets ADD COLUMN question_selection_mode VARCHAR(20) NOT NULL DEFAULT 'auto'"
                ))
                db.session.commit()
                print("[OK] Colonne 'question_selection_mode' ajoutee avec succes")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print("[INFO] La colonne 'question_selection_mode' existe deja")
                    db.session.rollback()
                else:
                    raise
            
            # 2. Créer la table d'association quiz_rule_set_questions
            print("[ETAPE 2] Creation de la table 'quiz_rule_set_questions'...")
            try:
                db.session.execute(text("""
                    CREATE TABLE IF NOT EXISTS quiz_rule_set_questions (
                        rule_set_id INTEGER NOT NULL,
                        question_id INTEGER NOT NULL,
                        PRIMARY KEY (rule_set_id, question_id),
                        FOREIGN KEY (rule_set_id) REFERENCES quiz_rule_sets(id),
                        FOREIGN KEY (question_id) REFERENCES questions(id)
                    )
                """))
                db.session.commit()
                print("[OK] Table 'quiz_rule_set_questions' creee avec succes")
            except Exception as e:
                if "already exists" in str(e).lower():
                    print("[INFO] La table 'quiz_rule_set_questions' existe deja")
                    db.session.rollback()
                else:
                    raise
            
            # 3. Vérifier le nombre de règles existantes
            result = db.session.execute(text("SELECT COUNT(*) FROM quiz_rule_sets"))
            count = result.scalar()
            print(f"[STATS] {count} regles existantes dans la base de donnees")
            
            print("\n[SUCCES] Migration terminee avec succes !")
            print("\nResume des modifications :")
            print("  - Colonne 'question_selection_mode' ajoutee a 'quiz_rule_sets' (defaut: 'auto')")
            print("  - Table 'quiz_rule_set_questions' creee")
            print(f"  - {count} regles existantes conservees avec le mode 'auto' par defaut")
            
        except Exception as e:
            print(f"\n[ERREUR] Erreur lors de la migration : {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate()

