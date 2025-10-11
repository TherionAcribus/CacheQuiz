"""
Script pour initialiser la base de données avec des exemples de questions
"""
from app import app
from models import db, Question
from datetime import datetime

def init_database():
    """Créer les tables et ajouter des exemples de questions"""
    with app.app_context():
        # Créer toutes les tables
        db.create_all()
        print("✅ Tables créées avec succès!")
        
        # Vérifier s'il y a déjà des questions
        if Question.query.count() > 0:
            print("⚠️  La base de données contient déjà des questions.")
            response = input("Voulez-vous ajouter des exemples supplémentaires? (o/n): ")
            if response.lower() != 'o':
                return
        
        # Exemples de questions
        sample_questions = [
            {
                'author': 'Admin',
                'question_text': "Quelle est la taille d'un cache 'Micro'?",
                'possible_answers': "Plus petit qu'un film 35mm|||De la taille d'un film 35mm|||Entre un film 35mm et une boîte à chaussures|||Plus grand qu'une boîte à chaussures",
                'answer_images': "|||",
                'correct_answer': '2',
                'detailed_answer': "Un cache Micro est de la taille approximative d'un film 35mm. C'est l'une des plus petites tailles de geocaches.",
                'hint': "Pensez à un objet photo ancien",
                'broad_theme': 'Règles',
                'specific_theme': 'Tailles de caches',
                'country': None,
                'difficulty_level': 1,
                'is_published': True
            },
            {
                'author': 'Admin',
                'question_text': "Qu'est-ce qu'un 'FTF' en géocaching?",
                'possible_answers': "First To Find (Premier à trouver)|||Fast To Find (Rapide à trouver)|||Far To Find (Loin à trouver)|||Failed To Find (Échec de recherche)",
                'answer_images': "|||",
                'correct_answer': '1',
                'detailed_answer': "FTF signifie 'First To Find', c'est-à-dire être la première personne à trouver une cache après sa publication. C'est un honneur recherché par de nombreux géocacheurs!",
                'hint': "C'est un honneur pour les géocacheurs compétitifs",
                'broad_theme': 'Terminologie',
                'specific_theme': 'Acronymes',
                'country': None,
                'difficulty_level': 1,
                'is_published': True
            },
            {
                'author': 'Admin',
                'question_text': "Quel type de cache nécessite de résoudre une énigme avant de connaître les coordonnées?",
                'possible_answers': "Traditional Cache|||Multi-Cache|||Mystery Cache|||EarthCache",
                'answer_images': "|||",
                'correct_answer': '3',
                'detailed_answer': "Un Mystery Cache (ou Unknown Cache) nécessite de résoudre une énigme ou un puzzle pour obtenir les coordonnées finales. Les coordonnées publiées ne sont qu'un point de référence.",
                'hint': "Le nom contient le mot 'mystère'",
                'broad_theme': 'Types de caches',
                'specific_theme': 'Mystery Cache',
                'country': None,
                'difficulty_level': 2,
                'is_published': True
            }
        ]
        
        # Ajouter les questions d'exemple
        for q_data in sample_questions:
            question = Question(**q_data)
            db.session.add(question)
        
        db.session.commit()
        print(f"✅ {len(sample_questions)} questions d'exemple ajoutées avec succès!")
        print("\n🚀 Vous pouvez maintenant lancer l'application avec: python app.py")

if __name__ == '__main__':
    init_database()

