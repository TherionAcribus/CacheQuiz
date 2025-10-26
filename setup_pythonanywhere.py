#!/usr/bin/env python3
"""
Script d'aide pour configurer PythonAnywhere
À exécuter localement pour afficher les commandes à copier sur PythonAnywhere
"""
import os

def show_pythonanywhere_setup():
    """Affiche les commandes à exécuter sur PythonAnywhere"""

    print("=" * 70)
    print("CONFIGURATION PYTHONANYWHERE - COMMANDES À COPIER")
    print("=" * 70)

    print("\n1. DANS LA CONSOLE BASH DE PYTHONANYWHERE, exécutez :")
    print()
    print("# Configurer les variables d'environnement")
    print("export FLASK_ENV=production")
    print("export DATABASE_URI=sqlite:///prod_geocaching_quiz.db")
    print("export SECRET_KEY=votre-cle-secrete-production-unique")
    print()
    print("# Optionnel : configuration email")
    print("# export MAIL_SERVER=votre-serveur-smtp")
    print("# export MAIL_PORT=587")
    print("# export MAIL_USERNAME=votre-email@domain.com")
    print("# export MAIL_PASSWORD=votre-mot-de-passe")
    print("# export MAIL_USE_TLS=1")
    print("# export MAIL_DEFAULT_SENDER=votre-email@domain.com")
    print()

    print("2. INITIALISER LA BASE DE DONNÉES :")
    print()
    print("cd /home/votre-username/votre-projet")
    print("python init_prod_db.py")
    print()

    print("3. DANS LES PARAMÈTRES WEB DE PYTHONANYWHERE :")
    print()
    print("   - Source code: /home/votre-username/votre-projet")
    print("   - Working directory: /home/votre-username/votre-projet")
    print("   - Virtualenv: sélectionnez votre environnement virtuel")
    print("   - WSGI configuration file: laissez vide (utilise app:app par défaut)")
    print()

    print("=" * 70)
    print("VÉRIFICATIONS APRÈS DÉPLOIEMENT")
    print("=" * 70)
    print()
    print("1. Vérifiez que le fichier prod_geocaching_quiz.db a été créé")
    print("2. Testez l'accès à votre application")
    print("3. Vérifiez les logs pour d'éventuelles erreurs")
    print()

if __name__ == '__main__':
    show_pythonanywhere_setup()
