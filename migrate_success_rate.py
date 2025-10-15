#!/usr/bin/env python3
"""
Script de migration pour convertir success_rate vers success_count
"""
from app import app
from models import db, Question

def migrate_success_stats():
    """Convertit les données existantes de success_rate vers success_count"""

    print("🔄 Migration des statistiques de succès...")

    with app.app_context():
        questions = Question.query.all()
        migrated_count = 0

        for question in questions:
            if hasattr(question, 'success_rate') and question.success_rate is not None and question.times_answered > 0:
                # Calculer success_count depuis success_rate
                calculated_success_count = round((question.success_rate / 100.0) * question.times_answered)

                # Mettre à jour success_count
                question.success_count = calculated_success_count
                migrated_count += 1

                print(f"  📊 Question {question.id}: {question.success_count}/{question.times_answered} succès")

        if migrated_count > 0:
            db.session.commit()
            print(f"✅ Migration terminée: {migrated_count} questions mises à jour")
        else:
            print("ℹ️ Aucune donnée à migrer")

if __name__ == '__main__':
    migrate_success_stats()
