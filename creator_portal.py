from flask import render_template
from auth import _ensure_creator_page_redirect


def creator_access_denied_page():
    """Page d'accès refusé pour l'espace Créateur."""
    return render_template('creator_access_denied_full.html')


def creator_home():
    """Hub de l'espace Créateur."""
    resp = _ensure_creator_page_redirect()
    if resp:
        return resp
    return render_template('creator_home.html')


