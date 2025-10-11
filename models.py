from datetime import datetime
from flask_sqlalchemy import SQLAlchemy

db = SQLAlchemy()


class BroadTheme(db.Model):
    __tablename__ = 'broad_themes'
    
    id = db.Column(db.Integer, primary_key=True)
    
    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Informations
    name = db.Column(db.String(100), nullable=False)  # Nom du thème
    description = db.Column(db.Text)  # Description optionnelle
    language = db.Column(db.String(10), nullable=False, default='fr')  # Code langue (fr, en, de, etc.)
    icon = db.Column(db.String(50))  # Emoji ou icône optionnelle
    color = db.Column(db.String(20))  # Couleur optionnelle pour l'affichage
    
    # Traduction
    translation_id = db.Column(db.Integer, db.ForeignKey('broad_themes.id'), nullable=True)
    
    # Relations
    translations = db.relationship('BroadTheme',
                                   backref=db.backref('original', remote_side=[id]),
                                   foreign_keys=[translation_id])
    
    # Relation inverse avec les questions
    questions = db.relationship('Question', back_populates='theme', lazy='dynamic')

    # Relation inverse avec les sous-thèmes
    specific_themes = db.relationship('SpecificTheme', back_populates='broad_theme', lazy='dynamic')
    
    def __repr__(self):
        return f'<BroadTheme {self.id}: {self.name} ({self.language})>'
    
    def to_dict(self):
        """Convertir le thème en dictionnaire pour JSON"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'language': self.language,
            'icon': self.icon,
            'color': self.color,
            'translation_id': self.translation_id,
            'question_count': self.questions.count()
        }


class SpecificTheme(db.Model):
    __tablename__ = 'specific_themes'

    id = db.Column(db.Integer, primary_key=True)

    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Informations
    name = db.Column(db.String(100), nullable=False)  # Nom du sous-thème
    description = db.Column(db.Text)  # Description optionnelle
    language = db.Column(db.String(10), nullable=False, default='fr')  # Code langue
    icon = db.Column(db.String(50))  # Emoji ou icône optionnelle
    color = db.Column(db.String(20))  # Couleur optionnelle

    # Relation avec le thème large
    broad_theme_id = db.Column(db.Integer, db.ForeignKey('broad_themes.id'), nullable=False)

    # Traduction
    translation_id = db.Column(db.Integer, db.ForeignKey('specific_themes.id'), nullable=True)

    # Relations
    translations = db.relationship('SpecificTheme',
                                   backref=db.backref('original', remote_side=[id]),
                                   foreign_keys=[translation_id])

    # Relation avec le thème large
    broad_theme = db.relationship('BroadTheme', back_populates='specific_themes')

    # Relation inverse avec les questions
    questions = db.relationship('Question', back_populates='specific_theme_obj', lazy='dynamic')

    def __repr__(self):
        return f'<SpecificTheme {self.id}: {self.name} (theme: {self.broad_theme.name if self.broad_theme else "None"})>'

    def to_dict(self):
        """Convertir le sous-thème en dictionnaire pour JSON"""
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'language': self.language,
            'icon': self.icon,
            'color': self.color,
            'broad_theme_id': self.broad_theme_id,
            'broad_theme_name': self.broad_theme.name if self.broad_theme else None,
            'translation_id': self.translation_id,
            'question_count': self.questions.count()
        }


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
    broad_theme_id = db.Column(db.Integer, db.ForeignKey('broad_themes.id'), nullable=True)
    specific_theme_id = db.Column(db.Integer, db.ForeignKey('specific_themes.id'), nullable=True)

    # Relations avec les thèmes
    theme = db.relationship('BroadTheme', back_populates='questions')
    specific_theme_obj = db.relationship('SpecificTheme', back_populates='questions')
    
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
            'broad_theme_id': self.broad_theme_id,
            'broad_theme_name': self.theme.name if self.theme else None,
            'specific_theme_id': self.specific_theme_id,
            'specific_theme_name': self.specific_theme_obj.name if self.specific_theme_obj else None,
            'country': self.country,
            'difficulty_level': self.difficulty_level,
            'success_rate': self.success_rate,
            'times_answered': self.times_answered,
            'translation_id': self.translation_id,
            'is_published': self.is_published
        }

