#!/usr/bin/env python3
"""
Script pour vérifier et corriger les utilisateurs avec profils admin mais sans mot de passe.
"""

from models import db, User, Profile
from flask import Flask
import os

def main():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///geocaching_quiz.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.app_context():
        db.init_app(app)

        print("Verification des utilisateurs avec profils admin...")

        # Trouver tous les utilisateurs avec un profil admin
        admin_users = User.query.filter(
            User.profile_id.isnot(None),
            Profile.id == User.profile_id,
            Profile.can_access_admin == True
        ).all()

        print(f"Trouve {len(admin_users)} utilisateur(s) avec profil admin")

        problematic_users = []
        for user in admin_users:
            if not user.password_hash:
                problematic_users.append(user)
                print(f"PROBLEME: {user.username} ({user.display_name}) - Profil: {user.profile.name} - PAS DE MOT DE PASSE")

        if problematic_users:
            print(f"\n{len(problematic_users)} utilisateur(s) ont un profil admin mais pas de mot de passe!")
            print("\nSolutions possibles:")
            print("1. Definir un mot de passe pour ces utilisateurs via l'interface admin")
            print("2. Changer leur profil vers un profil non-admin")
            print("3. Les desactiver temporairement")
            print("\nATTENTION: Ces utilisateurs ne pourront plus se connecter tant qu'ils n'ont pas de mot de passe!")
        else:
            print("OK: Tous les utilisateurs admin ont un mot de passe.")

if __name__ == '__main__':
    main()
