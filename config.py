import os
from dotenv import load_dotenv

# Charger les variables d'environnement
load_dotenv()

class Config:
    """Configuration de base"""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'dev-secret-key-change-in-production'
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI') or 'sqlite:///geocaching_quiz.db'
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
class DevelopmentConfig(Config):
    """Configuration de développement"""
    DEBUG = True
    
class ProductionConfig(Config):
    """Configuration de production"""
    DEBUG = False
    # En production, assurez-vous d'utiliser une vraie base de données
    # SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URI') or 'postgresql://user:pass@localhost/dbname'

config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'default': DevelopmentConfig
}

