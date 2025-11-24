from flask import render_template, request
from models import db, Country
from auth import _ensure_admin_page_redirect, _ensure_perm_api
from datetime import datetime


def countries():
    """Page de gestion des pays"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    return render_template('countries.html')


def list_countries_api():
    """Retourner la liste des pays en HTML (pour HTMX)"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    search = request.args.get('search', '')
    query = Country.query

    if search:
        query = query.filter(Country.name.like(f'%{search}%'))

    countries = query.order_by(Country.name).all()
    return render_template('countries_list.html', countries=countries)


def new_country():
    """Formulaire pour créer un nouveau pays"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    countries = Country.query.order_by(Country.name).all()
    return render_template('country_form.html', country=None, countries=countries)


def edit_country(country_id):
    """Formulaire pour éditer un pays"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    country = Country.query.get_or_404(country_id)
    countries = Country.query.order_by(Country.name).all()
    return render_template('country_form.html', country=country, countries=countries)


def create_country():
    """Créer un nouveau pays"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        data = request.form

        country = Country(
            name=data.get('name'),
            code=data.get('code'),
            flag=data.get('flag'),
            language=data.get('language', 'fr'),
            description=data.get('description'),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None
        )

        db.session.add(country)
        db.session.commit()

        # Retourner la liste mise à jour
        countries = Country.query.order_by(Country.name).all()
        return render_template('countries_list.html', countries=countries)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def update_country(country_id):
    """Mettre à jour un pays existant"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        country = Country.query.get_or_404(country_id)
        data = request.form

        # Mettre à jour les champs
        country.name = data.get('name')
        country.code = data.get('code')
        country.flag = data.get('flag')
        country.language = data.get('language', 'fr')
        country.description = data.get('description')
        country.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        country.updated_at = datetime.utcnow()

        db.session.commit()

        # Retourner la liste mise à jour
        countries = Country.query.order_by(Country.name).all()
        return render_template('countries_list.html', countries=countries)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def delete_country(country_id):
    """Supprimer un pays"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        country = Country.query.get_or_404(country_id)

        # Vérifier si le pays est utilisé dans des questions
        question_count = country.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer ce pays : {question_count} question(s) l'utilisent encore.", 400

        db.session.delete(country)
        db.session.commit()

        countries = Country.query.order_by(Country.name).all()
        return render_template('countries_list.html', countries=countries)

    except Exception as e:
        return f"Erreur: {str(e)}", 400
