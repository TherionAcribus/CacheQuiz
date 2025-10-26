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

        print("\n[SUCCES] Base de données de production initialisée !")
        print("=" * 60)

        print("\n[INSTRUCTIONS] :")
        print("   Votre application est prête à être utilisée")
        print("   Les données de développement sont préservées")

if __name__ == '__main__':
    init_prod_database()
