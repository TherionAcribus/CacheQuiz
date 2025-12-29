from flask import render_template, request, g
from models import db, Question, User, BroadTheme, SpecificTheme, Country, ImageAsset, AnswerImageLink, Keyword, QuestionAnswerStat, UserQuestionStat, SavedQuestion, Conversation, ConversationParticipant, ConversationMessage
from auth import _ensure_admin_page_redirect, _ensure_perm_api, _deny_access, _has_perm
from datetime import datetime


def get_stats():
    """API endpoint pour récupérer les statistiques actuelles"""
    denied = _ensure_perm_api()
    if denied:
        return denied

    total_questions = Question.query.count()
    online_questions = Question.query.filter_by(is_published=True).count()

    return {
        'total_questions': total_questions,
        'online_questions': online_questions
    }


def new_question():
    """Formulaire pour créer une nouvelle question"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    if not _has_perm('can_create_question'):
        return _deny_access("Permission 'can_create_question' requise")
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
    return render_template('question_form.html', question=None, themes=themes, specific_themes=specific_themes, countries=countries, images=images)


def view_question(question_id):
    """Voir les détails d'une question"""
    question = Question.query.get_or_404(question_id)
    return render_template('question_detail.html', question=question)


def edit_question(question_id):
    """Formulaire pour éditer une question"""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    question = Question.query.get_or_404(question_id)
    can_any = _has_perm('can_update_delete_any_question')
    can_own = _has_perm('can_update_delete_own_question')
    if not (can_any or (can_own and getattr(g, 'current_user', None) and question.author_id == g.current_user.id)):
        user = getattr(g, 'current_user', None)
        return render_template('access_denied.html', reason="Permission 'can_update_delete_own_question' ou 'can_update_delete_any_question' requise", current_user=user), 200
    themes = BroadTheme.query.order_by(BroadTheme.name).all()
    specific_themes = SpecificTheme.query.join(BroadTheme).order_by(BroadTheme.name, SpecificTheme.name).all()
    countries = Country.query.order_by(Country.name).all()
    images = ImageAsset.query.order_by(ImageAsset.created_at.desc()).all()
    return render_template('question_form.html', question=question, themes=themes, specific_themes=specific_themes, countries=countries, images=images)


def create_question():
    """Créer une nouvelle question"""
    try:
        denied = _ensure_perm_api('can_create_question')
        if denied:
            return denied
        data = request.form

        # Traiter les réponses possibles (en conservant l'index des réponses retenues)
        possible_answers = []
        answer_images_per_answer = []  # aligné sur possible_answers ('' si pas d'image)
        links_to_add = []  # liste de tuples (answer_index, image_id)
        i = 1
        current_index = 0
        while f'answer_{i}' in data:
            answer = (data.get(f'answer_{i}', '') or '').strip()
            answer_image_token = (data.get(f'answer_image_id_{i}', '') or '').strip()
            if answer or answer_image_token:
                current_index += 1
                possible_answers.append(answer)
                if answer_image_token.isdigit():
                    image_id_int = int(answer_image_token)
                    answer_images_per_answer.append(str(image_id_int))
                    links_to_add.append((current_index, image_id_int))
                else:
                    answer_images_per_answer.append('')
            i += 1

        # Attribuer l'auteur en fonction des droits
        if _has_perm('can_update_delete_any_question') and (data.get('author_id') or '').isdigit():
            author_id = int(data.get('author_id'))
        else:
            author_id = g.current_user.id if getattr(g, 'current_user', None) else None

        question = Question(
            author_id=author_id,
            question_text=data.get('question_text'),
            possible_answers='|||'.join(possible_answers),
            answer_images='|||'.join(answer_images_per_answer),
            correct_answer=data.get('correct_answer'),
            detailed_answer=data.get('detailed_answer'),
            hint=data.get('hint'),
            source=data.get('source').strip() if data.get('source') else None,
            detailed_answer_image_id=int(data.get('detailed_answer_image_id')) if data.get('detailed_answer_image_id') else None,
            broad_theme_id=int(data.get('broad_theme_id')) if data.get('broad_theme_id') else None,
            specific_theme_id=int(data.get('specific_theme_id')) if data.get('specific_theme_id') else None,
            difficulty_level=int(data.get('difficulty_level', 1)),
            translation_id=int(data.get('translation_id')) if data.get('translation_id') else None,
            is_published=data.get('is_published') == 'on',
            is_private=data.get('is_private') == 'on'
        )

        # Gérer les pays (relation many-to-many)
        country_ids = request.form.getlist('countries')
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            question.countries = countries

        # Gérer l'image de la question (relation many-to-many, une seule image)
        question_image_id = request.form.get('question_image_id')
        if question_image_id:
            try:
                img = ImageAsset.query.get(int(question_image_id))
                if img:
                    question.images = [img]
            except ValueError:
                pass
        else:
            question.images = []

        # Gérer les mots-clés (relation many-to-many)
        keyword_ids = request.form.getlist('keywords')
        if keyword_ids:
            keywords = Keyword.query.filter(Keyword.id.in_([int(kid) for kid in keyword_ids if kid])).all()
            question.keywords = keywords

        db.session.add(question)
        db.session.flush()

        # Gérer les liens image->réponse (AnswerImageLink) avec index correct
        for answer_index, image_id in links_to_add:
            db.session.add(AnswerImageLink(question_id=question.id, answer_index=answer_index, image_id=image_id))

        db.session.commit()

        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def get_question_detail(question_id):
    """Récupérer le détail complet d'une question"""
    try:
        question = Question.query.get(question_id)
        if not question:
            return {'error': 'Question non trouvée'}, 404

        return question.to_dict()

    except Exception as e:
        print(f"Erreur lors de la récupération de la question {question_id}: {e}")
        return {'error': str(e)}, 500


def update_question(question_id):
    """Mettre à jour une question existante"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        question = Question.query.get_or_404(question_id)
        can_any = _has_perm('can_update_delete_any_question')
        can_own = _has_perm('can_update_delete_own_question')
        if not (can_any or (can_own and getattr(g, 'current_user', None) and question.author_id == g.current_user.id)):
            return _deny_access("Permission 'can_update_delete_own_question' ou 'can_update_delete_any_question' requise")
        data = request.form

        # Traiter les réponses possibles (en conservant l'index des réponses retenues)
        possible_answers = []
        answer_images_per_answer = []  # aligné sur possible_answers ('' si pas d'image)
        links_to_add = []  # liste de tuples (answer_index, image_id)
        i = 1
        current_index = 0
        while f'answer_{i}' in data:
            answer = (data.get(f'answer_{i}', '') or '').strip()
            answer_image_token = (data.get(f'answer_image_id_{i}', '') or '').strip()
            if answer or answer_image_token:
                current_index += 1
                possible_answers.append(answer)
                if answer_image_token.isdigit():
                    image_id_int = int(answer_image_token)
                    answer_images_per_answer.append(str(image_id_int))
                    links_to_add.append((current_index, image_id_int))
                else:
                    answer_images_per_answer.append('')
            i += 1

        # Mettre à jour les champs
        # Changer l'auteur uniquement avec le droit global
        if can_any and (data.get('author_id') or '').isdigit():
            question.author_id = int(data.get('author_id'))
        question.question_text = data.get('question_text')
        question.possible_answers = '|||'.join(possible_answers)
        question.answer_images = '|||'.join(answer_images_per_answer)
        question.correct_answer = data.get('correct_answer')
        question.detailed_answer = data.get('detailed_answer')
        question.hint = data.get('hint')
        question.source = data.get('source').strip() if data.get('source') else None
        question.detailed_answer_image_id = int(data.get('detailed_answer_image_id')) if data.get('detailed_answer_image_id') else None
        question.broad_theme_id = int(data.get('broad_theme_id')) if data.get('broad_theme_id') else None
        question.specific_theme_id = int(data.get('specific_theme_id')) if data.get('specific_theme_id') else None
        question.difficulty_level = int(data.get('difficulty_level', 1))
        question.translation_id = int(data.get('translation_id')) if data.get('translation_id') else None
        question.is_published = data.get('is_published') == 'on'
        question.is_private = data.get('is_private') == 'on'
        question.updated_at = datetime.utcnow()

        # Gérer les pays (relation many-to-many)
        country_ids = request.form.getlist('countries')
        if country_ids:
            countries = Country.query.filter(Country.id.in_(country_ids)).all()
            question.countries = countries
        else:
            question.countries = []

        # Gérer l'image de la question (relation many-to-many, une seule image)
        question_image_id = request.form.get('question_image_id')
        if question_image_id:
            try:
                img = ImageAsset.query.get(int(question_image_id))
                if img:
                    question.images = [img]
            except ValueError:
                pass
        else:
            question.images = []

        # Gérer les mots-clés (relation many-to-many)
        keyword_ids = request.form.getlist('keywords')
        if keyword_ids:
            keywords = Keyword.query.filter(Keyword.id.in_([int(kid) for kid in keyword_ids if kid])).all()
            question.keywords = keywords
        else:
            question.keywords = []

        # Réinitialiser les liens image->réponse
        AnswerImageLink.query.filter_by(question_id=question.id).delete()
        db.session.flush()
        for answer_index, image_id in links_to_add:
            db.session.add(AnswerImageLink(question_id=question.id, answer_index=answer_index, image_id=image_id))

        db.session.commit()

        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        return render_template('questions_list.html', questions=questions)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def delete_question(question_id):
    """Supprimer une question"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        question = Question.query.get_or_404(question_id)
        
        # Vérification si la question est utilisée dans des règles de quiz
        # (exemple fictif, ajustez selon votre modèle de données réel si nécessaire)
        # if question.quiz_rules:
        #    return "Impossible de supprimer cette question car elle est utilisée dans des règles de quiz.", 400

        can_any = _has_perm('can_update_delete_any_question')
        can_own = _has_perm('can_update_delete_own_question')
        if not (can_any or (can_own and getattr(g, 'current_user', None) and question.author_id == g.current_user.id)):
            return _deny_access("Permission 'can_update_delete_own_question' ou 'can_update_delete_any_question' requise")
        
        # Supprimer d'abord les liens AnswerImageLink
        AnswerImageLink.query.filter_by(question_id=question.id).delete()
        
        # Supprimer les statistiques de réponses associées (QuestionAnswerStat)
        QuestionAnswerStat.query.filter_by(question_id=question.id).delete()
        
        # Supprimer les statistiques utilisateurs associées (UserQuestionStat)
        UserQuestionStat.query.filter_by(question_id=question.id).delete()
        
        # Supprimer les sauvegardes utilisateurs associées (SavedQuestion)
        SavedQuestion.query.filter_by(question_id=question.id).delete()
        
        # Supprimer les liens many-to-many si nécessaire (géré automatiquement par SQLAlchemy si configuré, sinon manuel)
        question.countries = []
        question.keywords = []
        question.images = []

        db.session.delete(question)
        db.session.commit()

        # Retourner la liste mise à jour
        questions = Question.query.order_by(Question.updated_at.desc()).all()
        
        # Compter pour mettre à jour les stats
        filtered_count = len(questions)
        total_count = Question.query.count()
        
        return render_template('questions_list.html', questions=questions, filtered_count=filtered_count, total_count=total_count)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return f"Erreur lors de la suppression: {str(e)}", 400


def toggle_question_status(question_id):
    """Changer le statut de publication d'une question"""
    try:
        denied = _ensure_perm_api()
        if denied:
            return denied
        question = Question.query.get_or_404(question_id)
        can_any = _has_perm('can_update_delete_any_question')
        can_own = _has_perm('can_update_delete_own_question')
        if not (can_any or (can_own and getattr(g, 'current_user', None) and question.author_id == g.current_user.id)):
            return _deny_access("Permission 'can_update_delete_own_question' ou 'can_update_delete_any_question' requise")
        new_val = not question.is_published
        question.is_published = new_val
        # Une question publiée ne doit pas rester privée (sinon elle n'entre jamais dans le pool public)
        if question.is_published:
            question.is_private = False
        question.updated_at = datetime.utcnow()

        # Si on publie une question, notifier le créateur via la conversation de publication (si applicable)
        if new_val and question.author_id:
            try:
                conv = Conversation.query.filter_by(context_type='question_publication', context_id=question.id).order_by(Conversation.created_at.desc()).first()
                if conv:
                    # S'assurer que l'auteur est participant
                    existing = ConversationParticipant.query.filter_by(conversation_id=conv.id, user_id=question.author_id).first()
                    if not existing:
                        db.session.add(ConversationParticipant(conversation_id=conv.id, user_id=question.author_id, last_read_at=None))
                    admin = getattr(g, 'current_user', None)
                    db.session.add(ConversationMessage(
                        conversation_id=conv.id,
                        sender_id=admin.id if admin else None,
                        content=f"✅ Question validée et publiée (Q{question.id}).",
                    ))
            except Exception:
                # On ne bloque pas la publication si la messagerie échoue
                pass

        db.session.commit()

        # Retourner uniquement le contenu de la cellule statut mis à jour
        return render_template('question_status_cell.html', question=question)

    except Exception as e:
        return f"Erreur: {str(e)}", 400


def _apply_sorting(query, sort_by, sort_order):
    """Appliquer le tri à la requête selon les paramètres donnés"""
    if sort_by == 'question_text':
        if sort_order == 'asc':
            return query.order_by(Question.question_text.asc())
        else:
            return query.order_by(Question.question_text.desc())
    elif sort_by == 'broad_theme':
        if sort_order == 'asc':
            return query.order_by(BroadTheme.name.asc().nulls_last())
        else:
            return query.order_by(BroadTheme.name.desc().nulls_last())
    elif sort_by == 'specific_theme':
        if sort_order == 'asc':
            return query.order_by(SpecificTheme.name.asc().nulls_last())
        else:
            return query.order_by(SpecificTheme.name.desc().nulls_last())
    elif sort_by == 'difficulty_level':
        if sort_order == 'asc':
            return query.order_by(Question.difficulty_level.asc())
        else:
            return query.order_by(Question.difficulty_level.desc())
    elif sort_by == 'is_published':
        if sort_order == 'asc':
            return query.order_by(Question.is_published.asc())
        else:
            return query.order_by(Question.is_published.desc())
    elif sort_by == 'created_at':
        if sort_order == 'asc':
            return query.order_by(Question.created_at.asc())
        else:
            return query.order_by(Question.created_at.desc())
    elif sort_by == 'author':
        if sort_order == 'asc':
            return query.order_by(User.username.asc().nulls_last())
        else:
            return query.order_by(User.username.desc().nulls_last())
    else:
        # Tri par défaut
        return query.order_by(Question.updated_at.desc())


def search_questions():
    """Rechercher des questions"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    query_param = request.args.get('q', '').strip()
    view = request.args.get('view', 'cards')
    sort_by = request.args.get('sort_by', 'updated_at')
    sort_order = request.args.get('sort_order', 'desc')

    base_query = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)

    if query_param:
        base_query = base_query.filter(
            db.or_(
                Question.question_text.contains(query_param),
                User.username.contains(query_param),
                BroadTheme.name.contains(query_param),
                SpecificTheme.name.contains(query_param)
            )
        )

    # Filtres avancés
    author_id = request.args.get('author_id', type=int)
    if author_id:
        base_query = base_query.filter(Question.author_id == author_id)

    broad_theme_id = request.args.get('broad_theme_id', type=int)
    if broad_theme_id:
        base_query = base_query.filter(Question.broad_theme_id == broad_theme_id)

    specific_theme_id = request.args.get('specific_theme_id', type=int)
    if specific_theme_id:
        base_query = base_query.filter(Question.specific_theme_id == specific_theme_id)

    difficulty_level = request.args.get('difficulty_level', type=int)
    if difficulty_level:
        base_query = base_query.filter(Question.difficulty_level == difficulty_level)

    keyword_id = request.args.get('keyword_id', type=int)
    if keyword_id:
        base_query = base_query.join(Question.keywords).filter(Keyword.id == keyword_id)

    questions = _apply_sorting(base_query, sort_by, sort_order).all()

    filtered_count = len(questions)
    total_count = Question.query.count()

    return render_template('questions_list.html', questions=questions, view=view, sort_by=sort_by, sort_order=sort_order, filtered_count=filtered_count, total_count=total_count)


def sort_questions():
    """Trier les questions"""
    denied = _ensure_perm_api()
    if denied:
        return denied
    view = request.args.get('view', 'cards')
    sort_by = request.args.get('sort_by', 'updated_at')
    query_param = request.args.get('q', '').strip()

    # Déterminer l'ordre de tri : si on clique sur la même colonne, on inverse l'ordre
    current_sort_by = request.args.get('current_sort_by', '')
    current_sort_order = request.args.get('current_sort_order', 'desc')

    if sort_by == current_sort_by:
        # Même colonne, on inverse l'ordre
        sort_order = 'asc' if current_sort_order == 'desc' else 'desc'
    else:
        # Nouvelle colonne, on commence par ascendant
        sort_order = 'asc'

    base_query = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)

    if query_param:
        base_query = base_query.filter(
            db.or_(
                Question.question_text.contains(query_param),
                User.username.contains(query_param),
                User.username.contains(query_param),
                BroadTheme.name.contains(query_param),
                SpecificTheme.name.contains(query_param)
            )
        )

    questions = _apply_sorting(base_query, sort_by, sort_order).all()

    filtered_count = len(questions)
    total_count = Question.query.count()

    return render_template('questions_list.html', questions=questions, view=view, sort_by=sort_by, sort_order=sort_order, filtered_count=filtered_count, total_count=total_count)
