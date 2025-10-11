from flask import Flask, render_template, request, jsonify, redirect, url_for
from models import db, Question, BroadTheme, SpecificTheme, User, Country
from datetime import datetime
import os

app = Flask(__name__)
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///geocaching_quiz.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['SECRET_KEY'] = 'dev-secret-key-change-in-production'

db.init_app(app)

# Créer les tables
with app.app_context():
    db.create_all()


@app.route('/')
def index():
    """Page d'accueil avec la liste des questions"""
    return render_template('index.html')


@app.route('/questions')
def list_questions():
    """Retourner la liste des questions en HTML (pour HTMX)"""
    questions = Question.query.order_by(Question.updated_at.desc()).all()
    return render_template('questions_list.html', questions=questions)


@app.route('/question/new')
def new_question():
    """Formulaire pour créer une nouvelle question"""
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
    countries = Country.query.order_by(Country.name).all()
    return render_template('question_form.html', question=None, themes=themes, specific_themes=specific_themes, users=users, countries=countries)


@app.route('/question/<int:question_id>')
def view_question(question_id):
    """Voir les détails d'une question"""
    question = Question.query.get_or_404(question_id)
    return render_template('question_detail.html', question=question)


@app.route('/question/<int:question_id>/edit')
def edit_question(question_id):
    """Formulaire pour éditer une question"""
    question = Question.query.get_or_404(question_id)
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
    countries = Country.query.order_by(Country.name).all()
    return render_template('question_form.html', question=question, themes=themes, specific_themes=specific_themes, users=users, countries=countries)


@app.route('/api/question', methods=['POST'])
def create_question():
    """Créer une nouvelle question"""
    try:
        data = request.form
        
        # Traiter les réponses possibles
        possible_answers = []
        answer_images = []
        i = 1
        while f'answer_{i}' in data:
            answer = data.get(f'answer_{i}', '').strip()
            if answer:
                possible_answers.append(answer)
                answer_images.append(data.get(f'answer_image_{i}', '').strip())
            i += 1
        
        question = Question(
            author_id=int(data.get('author_id')),
            question_text=data.get('question_text'),
            possible_answers='|||'.join(possible_answers),
            answer_images='|||'.join(answer_images),
            correct_answer=data.get('correct_answer'),
            detailed_answer=data.get('detailed_answer'),
            hint=data.get('hint'),
            broad_theme_id=int(data.get('broad_theme_id')) if data.get('broad_theme_id') else None,
            specific_theme_id=int(data.get('specific_theme_id')) if data.get('specific_theme_id') else None,
            difficulty_level=int(data.get('difficulty_level', 1)),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None,
            is_published=data.get('is_published') == 'on'
        )
        
        # Gérer les pays (relation many-to-many)
        country_ids = request.form.getlist('countries')
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            question.countries = countries
        
        db.session.add(question)
        db.session.commit()
        
        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/question/<int:question_id>', methods=['PUT', 'POST'])
def update_question(question_id):
    """Mettre à jour une question existante"""
    try:
        question = Question.query.get_or_404(question_id)
        data = request.form
        
        # Traiter les réponses possibles
        possible_answers = []
        answer_images = []
        i = 1
        while f'answer_{i}' in data:
            answer = data.get(f'answer_{i}', '').strip()
            if answer:
                possible_answers.append(answer)
                answer_images.append(data.get(f'answer_image_{i}', '').strip())
            i += 1
        
        # Mettre à jour les champs
        question.author_id = int(data.get('author_id'))
        question.question_text = data.get('question_text')
        question.possible_answers = '|||'.join(possible_answers)
        question.answer_images = '|||'.join(answer_images)
        question.correct_answer = data.get('correct_answer')
        question.detailed_answer = data.get('detailed_answer')
        question.hint = data.get('hint')
        question.broad_theme_id = int(data.get('broad_theme_id')) if data.get('broad_theme_id') else None
        question.specific_theme_id = int(data.get('specific_theme_id')) if data.get('specific_theme_id') else None
        question.difficulty_level = int(data.get('difficulty_level', 1))
        question.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        question.is_published = data.get('is_published') == 'on'
        question.updated_at = datetime.utcnow()
        
        # Gérer les pays (relation many-to-many)
        country_ids = request.form.getlist('countries')
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            question.countries = countries
        else:
            question.countries = []
        
        db.session.commit()
        
        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/question/<int:question_id>', methods=['DELETE'])
def delete_question(question_id):
    """Supprimer une question"""
    try:
        question = Question.query.get_or_404(question_id)
        db.session.delete(question)
        db.session.commit()
        
        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/questions/search')
def search_questions():
    """Rechercher des questions"""
    query = request.args.get('q', '').strip()
    
    if query:
        questions = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True).filter(
            db.or_(
                Question.question_text.contains(query),
                User.display_name.contains(query),
                User.username.contains(query),
                BroadTheme.name.contains(query),
                SpecificTheme.name.contains(query)
            )
        ).order_by(Question.updated_at.desc()).all()
    else:
        questions = Question.query.order_by(Question.updated_at.desc()).all()
    
    return render_template('questions_list.html', questions=questions)


# ===== Routes pour les thèmes =====

@app.route('/themes')
def themes_page():
    """Page de gestion des thèmes"""
    return render_template('themes.html')


@app.route('/api/themes')
def list_themes():
    """Retourner la liste des thèmes en HTML (pour HTMX)"""
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('themes_list.html', themes=themes)


@app.route('/theme/new')
def new_theme():
    """Formulaire pour créer un nouveau thème"""
    return render_template('theme_form.html', theme=None)


@app.route('/theme/<int:theme_id>/edit')
def edit_theme(theme_id):
    """Formulaire pour éditer un thème"""
    theme = BroadTheme.query.get_or_404(theme_id)
    return render_template('theme_form.html', theme=theme)


@app.route('/api/theme', methods=['POST'])
def create_theme():
    """Créer un nouveau thème"""
    try:
        data = request.form
        
        theme = BroadTheme(
            name=data.get('name'),
            description=data.get('description'),
            language=data.get('language', 'fr'),
            icon=data.get('icon'),
            color=data.get('color'),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None
        )
        
        db.session.add(theme)
        db.session.commit()
        
        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_list.html', themes=themes)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/theme/<int:theme_id>', methods=['PUT', 'POST'])
def update_theme(theme_id):
    """Mettre à jour un thème existant"""
    try:
        theme = BroadTheme.query.get_or_404(theme_id)
        data = request.form
        
        # Mettre à jour les champs
        theme.name = data.get('name')
        theme.description = data.get('description')
        theme.language = data.get('language', 'fr')
        theme.icon = data.get('icon')
        theme.color = data.get('color')
        theme.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        theme.updated_at = datetime.utcnow()
        
        db.session.commit()
        
        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_list.html', themes=themes)
    
    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/theme/<int:theme_id>', methods=['DELETE'])
def delete_theme(theme_id):
    """Supprimer un thème"""
    try:
        theme = BroadTheme.query.get_or_404(theme_id)

        # Vérifier si des questions utilisent ce thème
        question_count = theme.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer ce thème : {question_count} question(s) l'utilisent encore.", 400

        db.session.delete(theme)
        db.session.commit()

        # Retourner la liste mise à jour
        themes = BroadTheme.query.order_by(BroadTheme.name).all()
        return render_template('themes_list.html', themes=themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


# ===== Routes pour les sous-thèmes =====

@app.route('/specific-themes')
def specific_themes_page():
    """Page de gestion des sous-thèmes"""
    return render_template('specific_themes.html')


@app.route('/api/specific-themes')
def list_specific_themes():
    """Retourner la liste des sous-thèmes en HTML (pour HTMX)"""
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    return render_template('specific_themes_list.html', specific_themes=specific_themes)


@app.route('/specific-theme/new')
def new_specific_theme():
    """Formulaire pour créer un nouveau sous-thème"""
    broad_themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('specific_theme_form.html', specific_theme=None, broad_themes=broad_themes)


@app.route('/specific-theme/<int:specific_theme_id>/edit')
def edit_specific_theme(specific_theme_id):
    """Formulaire pour éditer un sous-thème"""
    specific_theme = SpecificTheme.query.get_or_404(specific_theme_id)
    broad_themes = BroadTheme.query.order_by(BroadTheme.name).all()
    return render_template('specific_theme_form.html', specific_theme=specific_theme, broad_themes=broad_themes)


@app.route('/api/specific-theme', methods=['POST'])
def create_specific_theme():
    """Créer un nouveau sous-thème"""
    try:
        data = request.form

        specific_theme = SpecificTheme(
            name=data.get('name'),
            description=data.get('description'),
            language=data.get('language', 'fr'),
            icon=data.get('icon'),
            color=data.get('color'),
            broad_theme_id=int(data.get('broad_theme_id')),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None
        )

        db.session.add(specific_theme)
        db.session.commit()

        # Retourner la liste mise à jour
        specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
        return render_template('specific_themes_list.html', specific_themes=specific_themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/specific-theme/<int:specific_theme_id>', methods=['PUT', 'POST'])
def update_specific_theme(specific_theme_id):
    """Mettre à jour un sous-thème existant"""
    try:
        specific_theme = SpecificTheme.query.get_or_404(specific_theme_id)
        data = request.form

        # Mettre à jour les champs
        specific_theme.name = data.get('name')
        specific_theme.description = data.get('description')
        specific_theme.language = data.get('language', 'fr')
        specific_theme.icon = data.get('icon')
        specific_theme.color = data.get('color')
        specific_theme.broad_theme_id = int(data.get('broad_theme_id'))
        specific_theme.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        specific_theme.updated_at = datetime.utcnow()

        db.session.commit()

        # Retourner la liste mise à jour
        specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
        return render_template('specific_themes_list.html', specific_themes=specific_themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/specific-theme/<int:specific_theme_id>', methods=['DELETE'])
def delete_specific_theme(specific_theme_id):
    """Supprimer un sous-thème"""
    try:
        specific_theme = SpecificTheme.query.get_or_404(specific_theme_id)

        # Vérifier si des questions utilisent ce sous-thème
        question_count = specific_theme.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer ce sous-thème : {question_count} question(s) l'utilisent encore.", 400

        db.session.delete(specific_theme)
        db.session.commit()

        # Retourner la liste mise à jour
        specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
        return render_template('specific_themes_list.html', specific_themes=specific_themes)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/specific-themes/for-theme/')
def get_specific_themes_for_broad_theme():
    """Obtenir les sous-thèmes pour un thème large (retourne HTML pour HTMX)"""
    broad_theme_id = request.args.get('broad_theme_id')
    if broad_theme_id and broad_theme_id.isdigit():
        specific_themes = SpecificTheme.query.filter_by(broad_theme_id=int(broad_theme_id)).order_by(SpecificTheme.name).all()
    else:
        specific_themes = []
    return render_template('specific_theme_options.html', specific_themes=specific_themes)


# ===== Routes pour les utilisateurs =====

@app.route('/users')
def users_page():
    """Page de gestion des utilisateurs"""
    return render_template('users.html')


@app.route('/api/users')
def list_users():
    """Retourner la liste des utilisateurs en HTML (pour HTMX)"""
    users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
    return render_template('users_list.html', users=users)


@app.route('/user/new')
def new_user():
    """Formulaire pour créer un nouvel utilisateur"""
    return render_template('user_form.html', user=None)


@app.route('/user/<int:user_id>/edit')
def edit_user(user_id):
    """Formulaire pour éditer un utilisateur"""
    user = User.query.get_or_404(user_id)
    return render_template('user_form.html', user=user)


@app.route('/api/user', methods=['POST'])
def create_user():
    """Créer un nouvel utilisateur"""
    try:
        data = request.form

        user = User(
            username=data.get('username'),
            email=data.get('email') or None,
            display_name=data.get('display_name'),
            is_active=data.get('is_active') == 'on'
        )

        db.session.add(user)
        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/user/<int:user_id>', methods=['PUT', 'POST'])
def update_user(user_id):
    """Mettre à jour un utilisateur existant"""
    try:
        user = User.query.get_or_404(user_id)
        data = request.form

        # Mettre à jour les champs
        user.username = data.get('username')
        user.email = data.get('email') or None
        user.display_name = data.get('display_name')
        user.is_active = data.get('is_active') == 'on'

        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


@app.route('/api/user/<int:user_id>', methods=['DELETE'])
def delete_user(user_id):
    """Désactiver un utilisateur (soft delete)"""
    try:
        user = User.query.get_or_404(user_id)

        # Vérifier si l'utilisateur a des questions
        question_count = user.questions.count()
        if question_count > 0:
            return f"Impossible de supprimer cet utilisateur : {question_count} question(s) lui appartiennent encore.", 400

        # Soft delete : désactiver au lieu de supprimer
        user.is_active = False
        db.session.commit()

        # Retourner la liste mise à jour
        users = User.query.filter_by(is_active=True).order_by(User.display_name).all()
        return render_template('users_list.html', users=users)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


# ============ Routes pour la gestion des Pays ============

@app.route('/countries')
def countries():
    """Page de gestion des pays"""
    return render_template('countries.html')


@app.route('/api/countries')
def list_countries_api():
    """Retourner la liste des pays en HTML (pour HTMX)"""
    search = request.args.get('search', '')
    query = Country.query
    
    if search:
        query = query.filter(Country.name.like(f'%{search}%'))
    
    countries = query.order_by(Country.name).all()
    return render_template('countries_list.html', countries=countries)


@app.route('/country/new')
def new_country():
    """Formulaire pour créer un nouveau pays"""
    countries = Country.query.order_by(Country.name).all()
    return render_template('country_form.html', country=None, countries=countries)


@app.route('/country/<int:country_id>/edit')
def edit_country(country_id):
    """Formulaire pour éditer un pays"""
    country = Country.query.get_or_404(country_id)
    countries = Country.query.order_by(Country.name).all()
    return render_template('country_form.html', country=country, countries=countries)


@app.route('/api/country', methods=['POST'])
def create_country():
    """Créer un nouveau pays"""
    try:
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


@app.route('/api/country/<int:country_id>', methods=['PUT', 'POST'])
def update_country(country_id):
    """Mettre à jour un pays existant"""
    try:
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


@app.route('/api/country/<int:country_id>', methods=['DELETE'])
def delete_country(country_id):
    """Supprimer un pays"""
    try:
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


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

