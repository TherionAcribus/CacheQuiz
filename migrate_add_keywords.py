"""
Migration pour ajouter le modèle Keyword (mots-clés/sujets précis) aux questions et quiz

Cette migration ajoute :
1. Table 'keywords' pour stocker les mots-clés/sujets précis
2. Table d'association 'question_keywords' pour lier les questions aux mots-clés
3. Table d'association 'quiz_rule_set_keywords' pour lier les règles de quiz aux mots-clés
4. Colonnes dans 'quiz_rule_sets' pour gérer les doublons de mots-clés

Usage:
    python migrate_add_keywords.py
"""

from app import app, db
from models import Keyword, Question, QuizRuleSet
from sqlalchemy import text

def migrate():
    with app.app_context():
        # Créer la table keywords
        print("Création de la table 'keywords'...")
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS keywords (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
                name VARCHAR(100) NOT NULL,
                description TEXT,
                language VARCHAR(10) NOT NULL DEFAULT 'fr',
                translation_id INTEGER,
                FOREIGN KEY (translation_id) REFERENCES keywords(id)
            )
        """))
        
        # Créer la table d'association question_keywords
        print("Création de la table d'association 'question_keywords'...")
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS question_keywords (
                question_id INTEGER NOT NULL,
                keyword_id INTEGER NOT NULL,
                PRIMARY KEY (question_id, keyword_id),
                FOREIGN KEY (question_id) REFERENCES questions(id) ON DELETE CASCADE,
                FOREIGN KEY (keyword_id) REFERENCES keywords(id) ON DELETE CASCADE
            )
        """))
        
        # Créer la table d'association quiz_rule_set_keywords
        print("Création de la table d'association 'quiz_rule_set_keywords'...")
        db.session.execute(text("""
            CREATE TABLE IF NOT EXISTS quiz_rule_set_keywords (
                rule_set_id INTEGER NOT NULL,
                keyword_id INTEGER NOT NULL,
                PRIMARY KEY (rule_set_id, keyword_id),
                FOREIGN KEY (rule_set_id) REFERENCES quiz_rule_sets(id) ON DELETE CASCADE,
                FOREIGN KEY (keyword_id) REFERENCES keywords(id) ON DELETE CASCADE
            )
        """))
        
        # Ajouter les nouvelles colonnes à quiz_rule_sets
        print("Ajout des colonnes 'prevent_duplicate_keywords' et 'use_all_keywords' à 'quiz_rule_sets'...")
        try:
            db.session.execute(text("""
                ALTER TABLE quiz_rule_sets 
                ADD COLUMN prevent_duplicate_keywords BOOLEAN NOT NULL DEFAULT 1
            """))
        except Exception as e:
            print(f"  Colonne 'prevent_duplicate_keywords' déjà existante ou erreur : {e}")
        
        try:
            db.session.execute(text("""
                ALTER TABLE quiz_rule_sets 
                ADD COLUMN use_all_keywords BOOLEAN NOT NULL DEFAULT 1
            """))
        except Exception as e:
            print(f"  Colonne 'use_all_keywords' déjà existante ou erreur : {e}")
        
        db.session.commit()
        print("✓ Migration terminée avec succès!")
        
        # Afficher quelques statistiques
        keyword_count = db.session.query(Keyword).count()
        print(f"\nStatistiques :")
        print(f"  - Mots-clés existants : {keyword_count}")
        print(f"  - Questions totales : {db.session.query(Question).count()}")
        print(f"  - Règles de quiz : {db.session.query(QuizRuleSet).count()}")

if __name__ == '__main__':
    print("="*70)
    print("Migration : Ajout des mots-clés (keywords) aux questions et quiz")
    print("="*70)
    print()
    
    response = input("Voulez-vous continuer avec cette migration ? (oui/non) : ")
    if response.lower() in ['oui', 'o', 'yes', 'y']:
        try:
            migrate()
            print("\n✓ Migration réussie !")
        except Exception as e:
            print(f"\n✗ Erreur lors de la migration : {e}")
            import traceback
            traceback.print_exc()
    else:
        print("Migration annulée.")

