#!/usr/bin/env python3
"""
Script d'initialisation de la base de données de production
À exécuter sur PythonAnywhere après le déploiement
"""
from app import app, db
import os

def init_prod_database():
    """Initialise la base de données de production"""

    print("=" * 60)
    print("[INIT PROD] INITIALISATION BASE DE DONNEES PRODUCTION")
    print("=" * 60)

    # Forcer la configuration production
    os.environ['FLASK_ENV'] = 'production'

    with app.app_context():
        print("\n[INFO] Configuration utilisée :")
        print(f"  - FLASK_ENV: {os.environ.get('FLASK_ENV', 'development')}")
        print(f"  - DATABASE_URI: {app.config.get('SQLALCHEMY_DATABASE_URI', 'Non défini')}")
        print(f"  - SECRET_KEY: {'Défini' if app.config.get('SECRET_KEY') else 'Non défini'}")

        print("\n[CREATION] Création des tables...")
        db.create_all()
        print("[OK] Tables créées")

        # Créer l'administrateur par défaut
        print("\n[ADMIN] Création de l'administrateur par défaut...")
        from werkzeug.security import generate_password_hash
        from models import Profile, User

        # S'assurer que le profil Administrateur existe
        admin_profile = Profile.query.filter_by(name='Administrateur').first()
        if not admin_profile:
            admin_profile = Profile(
                name='Administrateur',
                description="Accès complet à l'administration",
                can_access_admin=True,
                can_create_question=True,
                can_update_delete_own_question=True,
                can_update_delete_any_question=True,
                can_create_rule=True,
                can_update_delete_own_rule=True,
                can_update_delete_any_rule=True,
                can_manage_users=True,
                can_manage_profiles=True,
            )
            db.session.add(admin_profile)
            db.session.commit()
            print("[ADMIN] Profil Administrateur créé")

        # Vérifier si un admin existe déjà
        admin_count = User.query.filter_by(profile_id=admin_profile.id, is_active=True).count()
        if admin_count == 0:
            default_admin = User(
                username='admin',
                email='admin@geocaching-quiz.com',
                password_hash=generate_password_hash('admin123'),
                is_active=True,
                profile_id=admin_profile.id
            )
            db.session.add(default_admin)
            db.session.commit()
            print("[ADMIN] Administrateur par défaut créé: username='admin', password='admin123'")
        else:
            print("[ADMIN] Un administrateur existe déjà")

        print("\n[SUCCES] Base de données de production initialisée !")
        print("=" * 60)

        print("\n[INSTRUCTIONS] :")
        print("   Votre application est prête à être utilisée")
        print("   Les données de développement sont préservées")

if __name__ == '__main__':
    init_prod_database()
