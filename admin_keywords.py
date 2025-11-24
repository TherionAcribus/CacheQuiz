from flask import request
from models import db, Keyword
from unidecode import unidecode


def list_keywords_json():
    """Retourner la liste de tous les mots-clés en JSON (pour l'autocomplétion)"""
    try:
        keywords = Keyword.query.order_by(Keyword.name).all()
        return [kw.to_dict() for kw in keywords]
    except Exception as e:
        return {'error': str(e)}, 500


def create_keyword():
    """Créer un nouveau mot-clé"""
    try:
        # Pas besoin de vérifier les permissions ici car c'est appelé depuis le formulaire de question
        # qui a déjà ses propres contrôles de permissions
        name = request.form.get('name', '').strip()
        language = request.form.get('language', 'fr').strip()
        description = request.form.get('description', '').strip()

        # Validation
        if not name:
            return {'error': 'Le nom du mot-clé est requis'}, 400

        # Vérifier si le mot-clé existe déjà (normalisation pour éviter doublons)
        # Normaliser: enlever accents, espaces, traits d'union, mettre en minuscules
        normalized_name = unidecode(name.lower()).replace('-', '').replace(' ', '').replace('_', '')

        existing_keywords = Keyword.query.all()
        for existing in existing_keywords:
            existing_normalized = unidecode(existing.name.lower()).replace('-', '').replace(' ', '').replace('_', '')
            if existing_normalized == normalized_name:
                return {
                    'error': 'Un mot-clé similaire existe déjà',
                    'existing_keyword': existing.to_dict()
                }, 409

        # Créer le nouveau mot-clé
        keyword = Keyword(
            name=name,
            language=language,
            description=description if description else None
        )
        db.session.add(keyword)
        db.session.commit()

        return {
            'success': True,
            'keyword': keyword.to_dict(),
            'message': f'Mot-clé "{name}" créé avec succès'
        }, 201

    except Exception as e:
        db.session.rollback()
        return {'error': str(e)}, 500
