from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
import json

db = SQLAlchemy()


# Table d'association many-to-many entre Question et Country
question_countries = db.Table('question_countries',
    db.Column('question_id', db.Integer, db.ForeignKey('questions.id'), primary_key=True),
    db.Column('country_id', db.Integer, db.ForeignKey('countries.id'), primary_key=True)
)

# Table d'association many-to-many entre Question et Image (images complémentaires de la question)
question_images = db.Table('question_images',
    db.Column('question_id', db.Integer, db.ForeignKey('questions.id'), primary_key=True),
    db.Column('image_id', db.Integer, db.ForeignKey('images.id'), primary_key=True)
)


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


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)

    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

    # Informations de base
    username = db.Column(db.String(50), nullable=False, unique=True)  # Nom d'utilisateur unique
    email = db.Column(db.String(120), nullable=True)  # Email optionnel
    is_active = db.Column(db.Boolean, nullable=False, default=True)  # Utilisateur actif
    # Authentification (optionnelle): si non défini, l'utilisateur peut jouer via pseudo sans mot de passe
    password_hash = db.Column(db.String(255), nullable=True)
    # Rôle basique
    is_admin = db.Column(db.Boolean, nullable=False, default=False)
    # Préférences utilisateur sérialisées (JSON)
    preferences_json = db.Column(db.Text, nullable=True)

    # Profil et permissions
    profile_id = db.Column(db.Integer, db.ForeignKey('profiles.id'), nullable=True)
    profile = db.relationship('Profile', backref=db.backref('users', lazy='dynamic'))

    # Relation inverse avec les questions
    questions = db.relationship('Question', back_populates='author_user', lazy='dynamic')

    def __repr__(self):
        return f'<User {self.id}: {self.username}>'

    def to_dict(self):
        """Convertir l'utilisateur en dictionnaire pour JSON"""
        return {
            'id': self.id,
            'username': self.username,
            'email': self.email,
            'is_active': self.is_active,
            'is_admin': self.is_admin,
            'profile_id': self.profile_id,
            'profile_name': self.profile.name if self.profile else None,
            'question_count': self.questions.count(),
            'created_at': self.created_at.isoformat() if self.created_at else None
        }

    # Préférences (helpers)
    def get_preferences(self):
        try:
            return json.loads(self.preferences_json or '{}')
        except Exception:
            return {}

    def set_preferences(self, prefs):
        try:
            self.preferences_json = json.dumps(prefs or {})
        except Exception:
            self.preferences_json = '{}'

    # ====== Permissions ======
    def has_perm(self, perm_attr: str) -> bool:
        """Retourne True si l'utilisateur possède la permission demandée.
        - Les admins (is_admin=True) ont tous les droits.
        - Sinon, on délègue au profil associé le booléen nommé perm_attr.
        """
        try:
            if not self or not self.is_active:
                return False
            if self.is_admin:
                return True
            if self.profile and hasattr(self.profile, perm_attr):
                return bool(getattr(self.profile, perm_attr))
            return False
        except Exception:
            return False

    def has_any_admin_perm(self) -> bool:
        """Vérifie si l'utilisateur a au moins une permission administrative."""
        if not self or not self.is_active:
            return False

        # Si c'est un admin, il a tous les droits
        if self.is_admin:
            return True

        # Si pas de profil, pas de droits admin
        if not self.profile:
            return False

        # Liste des permissions administratives
        admin_perms = [
            'can_access_admin',
            'can_create_question',
            'can_update_delete_own_question',
            'can_update_delete_any_question',
            'can_create_rule',
            'can_update_delete_own_rule',
            'can_update_delete_any_rule',
            'can_manage_users',
            'can_manage_profiles'
        ]

        # Vérifier si au moins une permission est True
        for perm in admin_perms:
            if hasattr(self.profile, perm) and getattr(self.profile, perm, False):
                return True
        return False


class Country(db.Model):
    __tablename__ = 'countries'

    id = db.Column(db.Integer, primary_key=True)

    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Informations
    name = db.Column(db.String(100), nullable=False)  # Nom du pays
    code = db.Column(db.String(10))  # Code ISO (FR, BE, CA, etc.)
    flag = db.Column(db.String(10))  # Emoji du drapeau
    language = db.Column(db.String(10), nullable=False, default='fr')  # Code langue
    description = db.Column(db.Text)  # Description optionnelle

    # Traduction
    translation_id = db.Column(db.Integer, db.ForeignKey('countries.id'), nullable=True)

    # Relations
    translations = db.relationship('Country',
                                   backref=db.backref('original', remote_side=[id]),
                                   foreign_keys=[translation_id])

    # Relation inverse avec les questions (many-to-many)
    questions = db.relationship('Question',
                                secondary=question_countries,
                                back_populates='countries',
                                lazy='dynamic')

    def __repr__(self):
        return f'<Country {self.id}: {self.flag} {self.name} ({self.code})>'

    def to_dict(self):
        """Convertir le pays en dictionnaire pour JSON"""
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'flag': self.flag,
            'language': self.language,
            'description': self.description,
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
    author_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_text = db.Column(db.Text, nullable=False)

    # Relation avec l'auteur
    author_user = db.relationship('User', back_populates='questions')
    
    # Réponses (stockées en JSON-like format, séparées par '|||')
    possible_answers = db.Column(db.Text, nullable=False)  # Format: "Réponse 1|||Réponse 2|||Réponse 3"
    # answer_images est conservé pour compatibilité, mais remplacé par AnswerImageLink
    answer_images = db.Column(db.Text)
    correct_answer = db.Column(db.String(10), nullable=False)  # Ex: "1", "2", "3", etc.
    detailed_answer = db.Column(db.Text)
    hint = db.Column(db.Text)
    
    # Thématiques
    broad_theme_id = db.Column(db.Integer, db.ForeignKey('broad_themes.id'), nullable=True)
    specific_theme_id = db.Column(db.Integer, db.ForeignKey('specific_themes.id'), nullable=True)

    # Relations avec les thèmes
    theme = db.relationship('BroadTheme', back_populates='questions')
    specific_theme_obj = db.relationship('SpecificTheme', back_populates='questions')
    
    # Relation avec les pays (many-to-many)
    countries = db.relationship('Country',
                                secondary=question_countries,
                                back_populates='questions',
                                lazy='subquery')
    
    # Images complémentaires liées à la question (many-to-many)
    images = db.relationship('ImageAsset',
                             secondary=question_images,
                             back_populates='questions',
                             lazy='subquery')
    
    # Images associées aux réponses (one-to-many via table dédiée)
    answer_image_links = db.relationship('AnswerImageLink',
                                         back_populates='question',
                                         cascade='all, delete-orphan',
                                         lazy='subquery')

    # Image pour la réponse détaillée
    detailed_answer_image = db.relationship('ImageAsset', lazy='subquery')
    
    # Difficulté
    difficulty_level = db.Column(db.Integer)  # 1-5 par exemple
    
    # Statistiques
    success_count = db.Column(db.Integer, default=0)  # Nombre de succès
    times_answered = db.Column(db.Integer, default=0)  # Nombre de fois répondue
    
    # Traduction et publication
    translation_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=True)
    is_published = db.Column(db.Boolean, default=False)

    # Source (optionnelle) - URL ou référence pour vérifier la réponse
    source = db.Column(db.Text)

    # Image pour la réponse détaillée (optionnelle)
    detailed_answer_image_id = db.Column(db.Integer, db.ForeignKey('images.id'), nullable=True)
    
    # Relation pour les traductions
    translations = db.relationship('Question',
                                   backref=db.backref('original', remote_side=[id]),
                                   foreign_keys=[translation_id])

    @property
    def success_rate(self):
        """Calcule le taux de succès en pourcentage"""
        if self.times_answered == 0:
            return 0.0
        return (self.success_count / self.times_answered) * 100.0

    def __repr__(self):
        return f'<Question {self.id}: {self.question_text[:50]}...>'
    
    def to_dict(self):
        """Convertir la question en dictionnaire pour JSON"""
        return {
            'id': self.id,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
            'author_id': self.author_id,
            'author_name': self.author_user.display_name if self.author_user else None,
            'question_text': self.question_text,
            'possible_answers': self.possible_answers.split('|||') if self.possible_answers else [],
            'answer_images_legacy': self.answer_images.split('|||') if self.answer_images else [],
            'answer_image_ids': [link.image_id for link in self.answer_image_links],
            'correct_answer': self.correct_answer,
            'detailed_answer': self.detailed_answer,
            'hint': self.hint,
            'broad_theme_id': self.broad_theme_id,
            'broad_theme_name': self.theme.name if self.theme else None,
            'specific_theme_id': self.specific_theme_id,
            'specific_theme_name': self.specific_theme_obj.name if self.specific_theme_obj else None,
            'countries': [{'id': c.id, 'name': c.name, 'code': c.code, 'flag': c.flag} for c in self.countries],
            'difficulty_level': self.difficulty_level,
            'success_count': self.success_count,
            'success_rate': self.success_rate,
            'times_answered': self.times_answered,
            'translation_id': self.translation_id,
            'is_published': self.is_published,
            'source': self.source,
            'detailed_answer_image': self.detailed_answer_image.to_dict() if self.detailed_answer_image else None
        }


class ImageAsset(db.Model):
    __tablename__ = 'images'

    id = db.Column(db.Integer, primary_key=True)

    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Métadonnées
    title = db.Column(db.String(200), nullable=False)
    filename = db.Column(db.String(255), nullable=False, unique=True)  # nom de fichier stocké
    mime_type = db.Column(db.String(100))
    size_bytes = db.Column(db.Integer)
    alt_text = db.Column(db.String(255))

    # Relations inverses
    questions = db.relationship('Question',
                                secondary=question_images,
                                back_populates='images',
                                lazy='dynamic')

    def __repr__(self):
        return f"<ImageAsset {self.id}: {self.title} ({self.filename})>"

    def to_dict(self):
        return {
            'id': self.id,
            'title': self.title,
            'filename': self.filename,
            'mime_type': self.mime_type,
            'size_bytes': self.size_bytes,
            'alt_text': self.alt_text,
            'created_at': self.created_at.isoformat() if self.created_at else None
        }


class AnswerImageLink(db.Model):
    __tablename__ = 'answer_image_links'

    id = db.Column(db.Integer, primary_key=True)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)
    answer_index = db.Column(db.Integer, nullable=False)  # 1,2,3,...
    image_id = db.Column(db.Integer, db.ForeignKey('images.id'), nullable=False)

    # Contraintes d'unicité: une seule image par index de réponse pour une question
    __table_args__ = (
        db.UniqueConstraint('question_id', 'answer_index', name='uq_question_answer_index'),
    )

    # Relations
    question = db.relationship('Question', back_populates='answer_image_links')
    image = db.relationship('ImageAsset')

    def __repr__(self):
        return f"<AnswerImageLink q={self.question_id} idx={self.answer_index} img={self.image_id}>"


# ===================== Modèle de Profil & Permissions =====================

class Profile(db.Model):
    __tablename__ = 'profiles'

    id = db.Column(db.Integer, primary_key=True)

    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Métadonnées
    name = db.Column(db.String(100), nullable=False, unique=True)
    description = db.Column(db.Text)

    # Accès général
    can_access_admin = db.Column(db.Boolean, nullable=False, default=False)

    # Questions (propriété = auteur)
    can_create_question = db.Column(db.Boolean, nullable=False, default=False)
    can_update_delete_own_question = db.Column(db.Boolean, nullable=False, default=False)
    can_update_delete_any_question = db.Column(db.Boolean, nullable=False, default=False)

    # Règles de quiz (propriété = created_by_user_id)
    can_create_rule = db.Column(db.Boolean, nullable=False, default=False)
    can_update_delete_own_rule = db.Column(db.Boolean, nullable=False, default=False)
    can_update_delete_any_rule = db.Column(db.Boolean, nullable=False, default=False)

    # Utilisateurs et Profils
    can_manage_users = db.Column(db.Boolean, nullable=False, default=False)
    can_manage_profiles = db.Column(db.Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<Profile {self.id}: {self.name}>"

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'description': self.description,
            'can_access_admin': self.can_access_admin,
            'can_create_question': self.can_create_question,
            'can_update_delete_own_question': self.can_update_delete_own_question,
            'can_update_delete_any_question': self.can_update_delete_any_question,
            'can_create_rule': self.can_create_rule,
            'can_update_delete_own_rule': self.can_update_delete_own_rule,
            'can_update_delete_any_rule': self.can_update_delete_any_rule,
            'can_manage_users': self.can_manage_users,
            'can_manage_profiles': self.can_manage_profiles,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'updated_at': self.updated_at.isoformat() if self.updated_at else None,
        }

# ===================== Modèle pour les ensembles de règles du quiz =====================

# Tables d'association pour lier un set de règles à des thèmes
quiz_rule_set_broad_themes = db.Table(
    'quiz_rule_set_broad_themes',
    db.Column('rule_set_id', db.Integer, db.ForeignKey('quiz_rule_sets.id'), primary_key=True),
    db.Column('broad_theme_id', db.Integer, db.ForeignKey('broad_themes.id'), primary_key=True)
)

quiz_rule_set_specific_themes = db.Table(
    'quiz_rule_set_specific_themes',
    db.Column('rule_set_id', db.Integer, db.ForeignKey('quiz_rule_sets.id'), primary_key=True),
    db.Column('specific_theme_id', db.Integer, db.ForeignKey('specific_themes.id'), primary_key=True)
)


class QuizRuleSet(db.Model):
    __tablename__ = 'quiz_rule_sets'

    id = db.Column(db.Integer, primary_key=True)

    # Métadonnées
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Identification et description
    name = db.Column(db.String(120), nullable=False)
    slug = db.Column(db.String(120), unique=True)
    description = db.Column(db.Text)
    comment = db.Column(db.Text)
    is_active = db.Column(db.Boolean, nullable=False, default=True)

    # Auteur / créateur
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    created_by_user = db.relationship('User', foreign_keys=[created_by_user_id])

    # Paramètres de quiz
    timer_seconds = db.Column(db.Integer, nullable=False, default=30)  # durée par question

    # Difficultés utilisées (liste) et quotas par difficulté (JSON string: {"1":5,"2":3,...})
    allowed_difficulties_csv = db.Column(db.String(50), nullable=True)
    questions_per_difficulty_json = db.Column(db.Text, nullable=True)

    # Thèmes utilisés (tous ou sélection)
    use_all_broad_themes = db.Column(db.Boolean, nullable=False, default=True)
    use_all_specific_themes = db.Column(db.Boolean, nullable=False, default=True)
    allowed_broad_themes = db.relationship(
        'BroadTheme',
        secondary=quiz_rule_set_broad_themes,
        lazy='subquery'
    )
    allowed_specific_themes = db.relationship(
        'SpecificTheme',
        secondary=quiz_rule_set_specific_themes,
        lazy='subquery'
    )

    # Scoring
    scoring_base_points = db.Column(db.Integer, nullable=False, default=1)  # points par question
    scoring_difficulty_bonus_type = db.Column(db.String(20), nullable=False, default='none')  # none|add|mult
    # JSON string: ex {"1":0, "2":1, "3":2} pour add ou {"1":1.0,"2":1.5}
    scoring_difficulty_bonus_map_json = db.Column(db.Text, nullable=True)
    combo_bonus_enabled = db.Column(db.Boolean, nullable=False, default=False)
    combo_step = db.Column(db.Integer, nullable=True)  # taille de palier de combo (ex: 3)
    combo_bonus_points = db.Column(db.Integer, nullable=True)  # points ajoutés par palier atteint
    perfect_quiz_bonus = db.Column(db.Integer, nullable=False, default=0)

    # Messages
    intro_message = db.Column(db.Text)
    success_message = db.Column(db.Text)

    # Utilitaires de sérialisation/lecture
    def get_questions_per_difficulty(self):
        try:
            return json.loads(self.questions_per_difficulty_json or '{}')
        except Exception:
            return {}

    def set_questions_per_difficulty(self, mapping):
        self.questions_per_difficulty_json = json.dumps(mapping or {})

    def get_difficulty_bonus_map(self):
        try:
            return json.loads(self.scoring_difficulty_bonus_map_json or '{}')
        except Exception:
            return {}

    def set_difficulty_bonus_map(self, mapping):
        self.scoring_difficulty_bonus_map_json = json.dumps(mapping or {})

    def get_allowed_difficulties(self):
        if not self.allowed_difficulties_csv:
            return []
        return [int(x) for x in self.allowed_difficulties_csv.split(',') if x.strip().isdigit()]

    def set_allowed_difficulties(self, difficulties_list):
        if not difficulties_list:
            self.allowed_difficulties_csv = None
        else:
            self.allowed_difficulties_csv = ','.join(str(int(d)) for d in sorted(set(difficulties_list)))

    def __repr__(self):
        return f"<QuizRuleSet {self.id}: {self.name} active={self.is_active}>"


# ===================== Statistiques par utilisateur et question =====================

class UserQuestionStat(db.Model):
    __tablename__ = 'user_question_stats'

    id = db.Column(db.Integer, primary_key=True)

    # Dates
    created_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, nullable=False, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Liens
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    question_id = db.Column(db.Integer, db.ForeignKey('questions.id'), nullable=False)

    # Données de stats
    times_answered = db.Column(db.Integer, nullable=False, default=0)
    success_count = db.Column(db.Integer, nullable=False, default=0)
    last_selected_answer = db.Column(db.String(10), nullable=True)
    last_is_correct = db.Column(db.Boolean, nullable=False, default=False)
    last_answered_at = db.Column(db.DateTime, nullable=True)

    __table_args__ = (
        db.UniqueConstraint('user_id', 'question_id', name='uq_user_question'),
    )

    # Relations
    user = db.relationship('User', backref=db.backref('question_stats', lazy='dynamic'))
    question = db.relationship('Question')

    def __repr__(self):
        return f"<UserQuestionStat u={self.user_id} q={self.question_id} times={self.times_answered} success={self.success_count}>"
