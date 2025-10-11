from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()

class Question(db.Model):
    __tablename__ = 'questions'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Informations de base
    author = db.Column(db.String(100), nullable=False)
    question_text = db.Column(db.Text, nullable=False)
    
    # Réponses (stockées en JSON-like format, séparées par '|||')
    possible_answers = db.Column(db.Text, nullable=False)  # Format: "Réponse 1|||Réponse 2|||Réponse 3"
    answer_images = db.Column(db.Text)  # URLs des images, séparées par '|||'
    correct_answer = db.Column(db.String(10), nullable=False)  # Ex: "1", "2", "3", etc.
    detailed_answer = db.Column(db.Text)
    hint = db.Column(db.Text)
    
    # Thématiques
    broad_theme = db.Column(db.String(100))  # Ex: "Règles", "Histoire", "Technique"
    specific_theme = db.Column(db.String(100))  # Ex: "Reviewers", "Types de caches", "GPS"
    
    # Localisation et difficulté
    country = db.Column(db.String(100))  # Pays spécifique si applicable
    difficulty_level = db.Column(db.Integer)  # 1-5 par exemple
    
    # Statistiques
    success_rate = db.Column(db.Float, default=0.0)  # Pourcentage de réussite
    times_answered = db.Column(db.Integer, default=0)  # Nombre de fois répondue
    
    # Traduction et publication
    translation_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=True)
    is_published = db.Column(db.Boolean, default=False)
    
    # Relation pour les traductions
    translations = db.relationship('Question', 
                                   backref=db.backref('original', remote_side=[id]),
                                   foreign_keys=[translation_id])
    
    def __repr__(self):
        return f'<Question {self.id}: {self.question_text[:50]}...>'
    
    def to_dict(self):
        """Convertir la question en dictionnaire pour JSON"""
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'author': self.author,
            'question_text': self.question_text,
            'possible_answers': self.possible_answers.split('|||') if self.possible_answers else [],
            'answer_images': self.answer_images.split('|||') if self.answer_images else [],
            'correct_answer': self.correct_answer,
            'detailed_answer': self.detailed_answer,
            'hint': self.hint,
            'broad_theme': self.broad_theme,
            'specific_theme': self.specific_theme,
            'country': self.country,
            'difficulty_level': self.difficulty_level,
            'success_rate': self.success_rate,
            'times_answered': self.times_answered,
            'translation_id': self.translation_id,
            'is_published': self.is_published
        }

