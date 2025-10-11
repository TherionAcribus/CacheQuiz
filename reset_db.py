"""
Script pour réinitialiser complètement la base de données
"""
from app import app
from models import db, Question, BroadTheme
import os

def reset_database():
    """Supprimer et recréer complètement la base de données"""

    print("=" * 70)
    print("[RESET] REINITIALISATION COMPLETE DE LA BASE DE DONNEES")
    print("=" * 70)

    # Supprimer le fichier de base de données s'il existe
    db_file = 'geocaching_quiz.db'
    if os.path.exists(db_file):
        print(f"[SUPPRESSION] Suppression de {db_file}")
        os.remove(db_file)
    else:
        print(f"[INFO] {db_file} n'existe pas")

    with app.app_context():
        print("\n[CREATION] Creation des tables...")

        # Créer toutes les tables avec le nouveau schéma
        db.create_all()
        print("[OK] Tables creees")

        # Créer les thèmes par défaut
        print("\n[THEMES] Creation des themes par defaut...")
        sample_themes = [
            {
                'name': 'Règles',
                'description': 'Questions sur les règles officielles du géocaching',
                'language': 'fr',
                'icon': '📖',
                'color': '#3b82f6'
            },
            {
                'name': 'Terminologie',
                'description': 'Acronymes et termes spécifiques au géocaching',
                'language': 'fr',
                'icon': '💬',
                'color': '#8b5cf6'
            },
            {
                'name': 'Types de caches',
                'description': 'Questions sur les différents types de geocaches',
                'language': 'fr',
                'icon': '📦',
                'color': '#ec4899'
            },
            {
                'name': 'Histoire',
                'description': 'Histoire et évolution du géocaching',
                'language': 'fr',
                'icon': '🕰️',
                'color': '#f59e0b'
            },
            {
                'name': 'Technique',
                'description': 'GPS, navigation, coordonnées',
                'language': 'fr',
                'icon': '⚙️',
                'color': '#10b981'
            },
            {
                'name': 'Communauté',
                'description': 'Events, méga-events, culture du géocaching',
                'language': 'fr',
                'icon': '👥',
                'color': '#06b6d4'
            }
        ]

        themes = {}
        for theme_data in sample_themes:
            theme = BroadTheme(**theme_data)
            db.session.add(theme)
            db.session.flush()
            themes[theme_data['name']] = theme.id
            print(f"   [CREE] {theme_data['name']} (ID: {theme.id})")

        db.session.commit()
        print(f"[OK] {len(sample_themes)} themes crees")

        # Créer des questions d'exemple
        print("\n[QUESTIONS] Creation des questions d'exemple...")
        sample_questions = [
            {
                'author': 'Admin',
                'question_text': "Quelle est la taille d'un cache 'Micro'?",
                'possible_answers': "Plus petit qu'un film 35mm|||De la taille d'un film 35mm|||Entre un film 35mm et une boîte à chaussures|||Plus grand qu'une boîte à chaussures",
                'answer_images': "|||",
                'correct_answer': '2',
                'detailed_answer': "Un cache Micro est de la taille approximative d'un film 35mm. C'est l'une des plus petites tailles de geocaches.",
                'hint': "Pensez à un objet photo ancien",
                'broad_theme_id': themes['Règles'],
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
                'broad_theme_id': themes['Terminologie'],
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
                'broad_theme_id': themes['Types de caches'],
                'specific_theme': 'Mystery Cache',
                'country': None,
                'difficulty_level': 2,
                'is_published': True
            }
        ]

        for q_data in sample_questions:
            question = Question(**q_data)
            db.session.add(question)
            print(f"   [CREE] Question: {q_data['question_text'][:50]}...")

        db.session.commit()
        print(f"[OK] {len(sample_questions)} questions crees")

        print("\n" + "=" * 70)
        print("[SUCCES] REINITIALISATION TERMINEE !")
        print("=" * 70)
        print("\n[INSTRUCTIONS] :")
        print("   Lancez maintenant : python app.py")
        print("   Puis allez sur : http://localhost:5000")
        print("   Et explorez la nouvelle section 'Themes' !")

if __name__ == '__main__':
    reset_database()
