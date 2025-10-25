"""
Script de migration pour ajouter le mode de sélection manuelle de questions,
le nombre minimum de bonnes réponses pour gagner, le message d'échec,
et la sélection de pays aux QuizRuleSet.

Ce script ajoute :
1. Une nouvelle colonne 'question_selection_mode' (auto/manual)
2. Une nouvelle colonne 'min_correct_answers_to_win' (0 = toujours gagné)
3. Une nouvelle colonne 'failure_message' (message affiché en cas d'échec)
4. Une nouvelle colonne 'use_all_countries' (True = tous les pays)
5. Une nouvelle table d'association 'quiz_rule_set_questions' pour lier
   les règles aux questions spécifiques sélectionnées manuellement
6. Une nouvelle table d'association 'quiz_rule_set_countries' pour lier
   les règles aux pays sélectionnés
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

            # 2. Ajouter la colonne min_correct_answers_to_win à la table quiz_rule_sets
            print("[ETAPE 1b] Ajout de la colonne 'min_correct_answers_to_win' a 'quiz_rule_sets'...")
            try:
                db.session.execute(text(
                    "ALTER TABLE quiz_rule_sets ADD COLUMN min_correct_answers_to_win INTEGER NOT NULL DEFAULT 0"
                ))
                db.session.commit()
                print("[OK] Colonne 'min_correct_answers_to_win' ajoutee avec succes")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print("[INFO] La colonne 'min_correct_answers_to_win' existe deja")
                    db.session.rollback()
                else:
                    raise

            # 3. Ajouter la colonne failure_message à la table quiz_rule_sets
            print("[ETAPE 1c] Ajout de la colonne 'failure_message' a 'quiz_rule_sets'...")
            try:
                db.session.execute(text(
                    "ALTER TABLE quiz_rule_sets ADD COLUMN failure_message TEXT"
                ))
                db.session.commit()
                print("[OK] Colonne 'failure_message' ajoutee avec succes")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print("[INFO] La colonne 'failure_message' existe deja")
                    db.session.rollback()
                else:
                    raise

            # 4. Ajouter la colonne use_all_countries
            print("[ETAPE 1d] Ajout de la colonne 'use_all_countries' a 'quiz_rule_sets'...")
            try:
                db.session.execute(text(
                    "ALTER TABLE quiz_rule_sets ADD COLUMN use_all_countries BOOLEAN NOT NULL DEFAULT 1"
                ))
                db.session.commit()
                print("[OK] Colonne 'use_all_countries' ajoutee avec succes")
            except Exception as e:
                if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                    print("[INFO] La colonne 'use_all_countries' existe deja")
                    db.session.rollback()
                else:
                    raise

            # 5. Ajouter les colonnes d'images optionnelles pour les messages
            print("[ETAPE 1e] Ajout des colonnes d'images (intro_image_id, success_image_id, failure_image_id) a 'quiz_rule_sets'...")
            for col in [
                ("intro_image_id", "INTEGER"),
                ("success_image_id", "INTEGER"),
                ("failure_image_id", "INTEGER"),
            ]:
                col_name, col_type = col
                try:
                    db.session.execute(text(
                        f"ALTER TABLE quiz_rule_sets ADD COLUMN {col_name} {col_type}"
                    ))
                    db.session.commit()
                    print(f"[OK] Colonne '{col_name}' ajoutee avec succes")
                except Exception as e:
                    if "duplicate column name" in str(e).lower() or "already exists" in str(e).lower():
                        print(f"[INFO] La colonne '{col_name}' existe deja")
                        db.session.rollback()
                    else:
                        raise

            # 6. Créer la table d'association quiz_rule_set_countries
            print("[ETAPE 1f] Creation de la table 'quiz_rule_set_countries'...")
            try:
                db.session.execute(text("""
                    CREATE TABLE quiz_rule_set_countries (
                        rule_set_id INTEGER NOT NULL,
                        country_id INTEGER NOT NULL,
                        PRIMARY KEY (rule_set_id, country_id),
                        FOREIGN KEY (rule_set_id) REFERENCES quiz_rule_sets (id),
                        FOREIGN KEY (country_id) REFERENCES countries (id)
                    )
                """))
                db.session.commit()
                print("[OK] Table 'quiz_rule_set_countries' creee avec succes")
            except Exception as e:
                if "table.*already exists" in str(e).lower() or "already exists" in str(e).lower():
                    print("[INFO] La table 'quiz_rule_set_countries' existe deja")
                    db.session.rollback()
                else:
                    raise
            
            # 7. Créer la table d'association quiz_rule_set_questions
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
            print("  - Colonne 'min_correct_answers_to_win' ajoutee a 'quiz_rule_sets' (defaut: 0)")
            print("  - Colonne 'failure_message' ajoutee a 'quiz_rule_sets'")
            print("  - Colonne 'use_all_countries' ajoutee a 'quiz_rule_sets' (defaut: True)")
            print("  - Colonnes d'images (intro_image_id, success_image_id, failure_image_id) ajoutees")
            print("  - Table 'quiz_rule_set_countries' creee")
            print("  - Table 'quiz_rule_set_questions' creee")
            print(f"  - {count} regles existantes conservees avec le mode 'auto' par defaut")
            
        except Exception as e:
            print(f"\n[ERREUR] Erreur lors de la migration : {e}")
            db.session.rollback()
            raise

if __name__ == '__main__':
    migrate()

