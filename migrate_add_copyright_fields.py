"""
Migration pour ajouter les champs de copyright aux images

Cette migration ajoute :
1. Colonne 'copyright_link' à la table 'images' pour stocker le lien vers la source
2. Colonne 'copyright_credits' à la table 'images' pour stocker les crédits

Usage:
    python migrate_add_copyright_fields.py
"""

from app import app, db
from models import ImageAsset
from sqlalchemy import text

def migrate():
    with app.app_context():
        # Ajouter la colonne copyright_link
        print("Ajout de la colonne 'copyright_link' à la table 'images'...")
        try:
            db.session.execute(text("""
                ALTER TABLE images
                ADD COLUMN copyright_link TEXT
            """))
        except Exception as e:
            print(f"  Colonne 'copyright_link' déjà existante ou erreur : {e}")

        # Ajouter la colonne copyright_credits
        print("Ajout de la colonne 'copyright_credits' à la table 'images'...")
        try:
            db.session.execute(text("""
                ALTER TABLE images
                ADD COLUMN copyright_credits TEXT
            """))
        except Exception as e:
            print(f"  Colonne 'copyright_credits' déjà existante ou erreur : {e}")

        db.session.commit()
        print("✓ Migration terminée avec succès!")

        # Afficher quelques statistiques
        image_count = db.session.query(ImageAsset).count()
        images_with_copyright = db.session.query(ImageAsset).filter(
            (ImageAsset.copyright_link.isnot(None)) |
            (ImageAsset.copyright_credits.isnot(None))
        ).count()

        print(f"\nStatistiques :")
        print(f"  - Images totales : {image_count}")
        print(f"  - Images avec informations copyright : {images_with_copyright}")

if __name__ == '__main__':
    print("="*70)
    print("Migration : Ajout des champs copyright aux images")
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
