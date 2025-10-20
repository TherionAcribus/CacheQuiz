#!/usr/bin/env python3
"""
Script pour corriger le profil Lecteur qui ne devrait pas avoir accès à l'admin.
"""

from models import db, Profile
from flask import Flask

def main():
    app = Flask(__name__)
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///geocaching_quiz.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

    with app.app_context():
        db.init_app(app)

        print("Correction du profil Lecteur...")

        lecteur = Profile.query.filter_by(name='Lecteur').first()
        if lecteur:
            if lecteur.can_access_admin:
                print("Le profil Lecteur avait can_access_admin=True, correction...")
                lecteur.can_access_admin = False
                db.session.commit()
                print("Profil Lecteur corrige.")
            else:
                print("Le profil Lecteur est deja correct.")
        else:
            print("Profil Lecteur non trouve.")

if __name__ == '__main__':
    main()
