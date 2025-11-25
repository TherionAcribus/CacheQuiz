from flask import send_from_directory
from flask import current_app as app


def uploaded_file(filename):
    """Sert les fichiers uploadés depuis le dossier UPLOAD_FOLDER."""
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


def sounds_file(filename):
    """Sert les fichiers audio depuis le dossier SOUNDS_FOLDER."""
    return send_from_directory(app.config['SOUNDS_FOLDER'], filename)
