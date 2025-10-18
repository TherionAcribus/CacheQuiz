#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script pour générer des questions de test pour le quiz geocaching
"""
from models import db, Question, User, BroadTheme, SpecificTheme, Country
from app import app
import random

# Contenu Lorem Ipsum pour générer des questions
lorem_questions = [
    "Qu'est-ce que le Lorem ipsum dolor sit amet?",
    "Pourquoi utilise-t-on du Lorem ipsum en design?",
    "Quelle est la signification historique du Lorem ipsum?",
    "Comment le Lorem ipsum facilite-t-il le travail des designers?",
    "Le Lorem ipsum est-il adapté à tous les projets créatifs?",
    "Quelles sont les origines antiques du Lorem ipsum?",
    "Le Lorem ipsum peut-il remplacer du contenu réel?",
    "Comment générer du Lorem ipsum de manière automatique?",
    "Le Lorem ipsum est-il utilisé uniquement dans l'imprimerie?",
    "Quelle longueur idéale pour un texte Lorem ipsum?",
    "Le Lorem ipsum respecte-t-il la grammaire latine?",
    "Peut-on personnaliser le Lorem ipsum selon ses besoins?",
    "Le Lorem ipsum facilite-t-il les tests de mise en page?",
    "Quelle est la différence entre Lorem ipsum et texte factice?",
    "Le Lorem ipsum est-il universellement reconnu?",
    "Comment le Lorem ipsum aide-t-il à éviter les distractions?",
    "Le Lorem ipsum peut-il être utilisé en plusieurs langues?",
    "Quelle est l'importance du Lorem ipsum dans le web design?",
    "Le Lorem ipsum évolue-t-il avec les technologies modernes?",
    "Peut-on créer ses propres variantes de Lorem ipsum?"
]

lorem_answers = [
    "Consectetur adipiscing elit",
    "Sed do eiusmod tempor incididunt",
    "Ut labore et dolore magna aliqua",
    "Enim ad minim veniam",
    "Quis nostrud exercitation ullamco",
    "Laboris nisi ut aliquip ex ea commodo",
    "Duis aute irure dolor in reprehenderit",
    "Voluptate velit esse cillum dolore",
    "Eu fugiat nulla pariatur",
    "Excepteur sint occaecat cupidatat"
]

def generate_question_text(theme_name, difficulty):
    """Génère un texte de question basé sur le thème et la difficulté"""
    base_questions = [
        f"Dans le domaine {theme_name.lower()}, quelle est la signification de ce concept Lorem ipsum?",
        f"Concernant {theme_name.lower()}, comment appliquer cette règle Lorem ipsum?",
        f"Quel est le rôle principal de cet élément dans {theme_name.lower()} selon Lorem ipsum?",
        f"Comment reconnaître une situation Lorem ipsum en {theme_name.lower()}?",
        f"Quelle est la meilleure pratique Lorem ipsum pour {theme_name.lower()}?"
    ]
    return random.choice(base_questions)

def generate_detailed_answer(theme_name, difficulty):
    """Génère une réponse détaillée"""
    answers = [
        f"La réponse détaillée concernant {theme_name.lower()} explique que Lorem ipsum dolor sit amet, consectetur adipiscing elit. Cette approche permet de mieux comprendre les mécanismes sous-jacents.",
        f"En {theme_name.lower()}, cette réponse Lorem ipsum révèle que sed do eiusmod tempor incididunt ut labore et dolore magna aliqua. C'est une méthode éprouvée depuis longtemps.",
        f"Pour maîtriser {theme_name.lower()}, il faut savoir que ut enim ad minim veniam, quis nostrud exercitation ullamco laboris nisi ut aliquip ex ea commodo consequat."
    ]
    return random.choice(answers)

def generate_hint(theme_name):
    """Génère un indice"""
    hints = [
        f"Pensez aux principes fondamentaux de {theme_name.lower()}",
        f"Consultez les règles de base de {theme_name.lower()}",
        f"Cette notion est essentielle en {theme_name.lower()}",
        f"Revoyez les concepts de {theme_name.lower()}"
    ]
    return random.choice(hints)

def get_random_answers(num_answers=4):
    """Génère des réponses aléatoires"""
    answers = random.sample(lorem_answers, num_answers)
    correct_index = random.randint(0, num_answers-1)
    return answers, str(correct_index + 1)

def create_questions():
    """Crée des questions pour tous les thèmes et difficultés"""
    app.app_context().push()

    # Récupérer les données existantes
    themes = BroadTheme.query.all()
    specific_themes = SpecificTheme.query.all()
    users = User.query.all()
    countries = Country.query.all()

    if not users:
        print("Aucun utilisateur trouvé!")
        return

    author = users[0]  # Utiliser le premier utilisateur (admin)

    # Créer des combinaisons valides : chaque sous-thème avec son thème parent
    valid_combinations = []
    for specific_theme in specific_themes:
        if specific_theme.broad_theme:
            valid_combinations.append((specific_theme.broad_theme, specific_theme))

    questions_created = 0
    # Créer plusieurs questions par combinaison (5 difficultés × 3 variantes = 15 par combinaison)
    total_questions = len(valid_combinations) * 5 * 3
    print(f"Création de {total_questions} questions...")

    for broad_theme, specific_theme in valid_combinations:
        for difficulty in range(1, 6):  # Difficultés 1 à 5
            # Créer 3 variantes par combinaison difficulté/thème pour plus de contenu
            for variant in range(3):
                # Générer le contenu
                question_text = generate_question_text(specific_theme.name, difficulty)
                answers, correct_answer = get_random_answers()
                detailed_answer = generate_detailed_answer(specific_theme.name, difficulty)
                hint = generate_hint(specific_theme.name)

                # Créer la question
                question = Question(
                    author_id=author.id,
                    question_text=f"{question_text} (Variante {variant+1})",
                    possible_answers='|||'.join(answers),
                    correct_answer=correct_answer,
                    detailed_answer=detailed_answer,
                    hint=hint,
                    broad_theme_id=broad_theme.id,
                    specific_theme_id=specific_theme.id,
                    difficulty_level=difficulty,
                    is_published=True,  # Publier toutes les questions de test
                    source="Test automatique - Lorem Ipsum"
                )

                # Ajouter des pays aléatoirement (1-3 pays par question)
                num_countries = random.randint(1, min(3, len(countries)))
                selected_countries = random.sample(countries, num_countries)
                question.countries = selected_countries

                db.session.add(question)
                questions_created += 1

                if questions_created % 100 == 0:
                    print(f"Créé {questions_created}/{total_questions} questions...")
                    db.session.commit()

    # Commit final
    db.session.commit()
    print(f"Terminé ! {questions_created} questions créées avec succès.")

if __name__ == "__main__":
    create_questions()
