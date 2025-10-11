from flask import Flask, render_template, request, jsonify, redirect, url_for
from models import db, Question
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
    return render_template('question_form.html', question=None)


@app.route('/question/<int:question_id>')
def view_question(question_id):
    """Voir les détails d'une question"""
    question = Question.query.get_or_404(question_id)
    return render_template('question_detail.html', question=question)


@app.route('/question/<int:question_id>/edit')
def edit_question(question_id):
    """Formulaire pour éditer une question"""
    question = Question.query.get_or_404(question_id)
    return render_template('question_form.html', question=question)


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
            author=data.get('author'),
            question_text=data.get('question_text'),
            possible_answers='|||'.join(possible_answers),
            answer_images='|||'.join(answer_images),
            correct_answer=data.get('correct_answer'),
            detailed_answer=data.get('detailed_answer'),
            hint=data.get('hint'),
            broad_theme=data.get('broad_theme'),
            specific_theme=data.get('specific_theme'),
            country=data.get('country'),
            difficulty_level=int(data.get('difficulty_level', 1)),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None,
            is_published=data.get('is_published') == 'on'
        )
        
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
        question.author = data.get('author')
        question.question_text = data.get('question_text')
        question.possible_answers = '|||'.join(possible_answers)
        question.answer_images = '|||'.join(answer_images)
        question.correct_answer = data.get('correct_answer')
        question.detailed_answer = data.get('detailed_answer')
        question.hint = data.get('hint')
        question.broad_theme = data.get('broad_theme')
        question.specific_theme = data.get('specific_theme')
        question.country = data.get('country')
        question.difficulty_level = int(data.get('difficulty_level', 1))
        question.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        question.is_published = data.get('is_published') == 'on'
        question.updated_at = datetime.utcnow()
        
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
        questions = Question.query.filter(
            db.or_(
                Question.question_text.contains(query),
                Question.author.contains(query),
                Question.broad_theme.contains(query),
                Question.specific_theme.contains(query)
            )
        ).order_by(Question.updated_at.desc()).all()
    else:
        questions = Question.query.order_by(Question.updated_at.desc()).all()
    
    return render_template('questions_list.html', questions=questions)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)

