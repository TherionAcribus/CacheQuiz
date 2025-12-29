import random
from flask import render_template, request, redirect, url_for, session, g
from models import db, Question, QuizRuleSet, UserQuestionStat, QuestionAnswerStat, UserQuizSession, BroadTheme, SpecificTheme, AnswerImageLink
from quiz_playlist_generation import _apply_quiz_filters, _generate_quiz_playlist, get_rule_set_stats
from datetime import datetime


def _quiz_session_keys(rule_set_slug: str):
    """Construit des clés de session isolées par utilisateur et par set.
    Retourne (playlist_key, index_key, score_key, correct_key, breakdown_key, streak_key, perfect_key, user_id_str)
    """
    user_id_str = str(g.current_user.id) if getattr(g, 'current_user', None) else 'anon'
    prefix = f"{user_id_str}:{rule_set_slug}"
    playlist_key = f"quiz_playlist:{prefix}"
    index_key = f"quiz_playlist_index:{prefix}"
    score_key = f"quiz_score:{prefix}"
    correct_key = f"quiz_correct_answers:{prefix}"
    breakdown_key = f"quiz_score_breakdown:{prefix}"
    streak_key = f"quiz_combo_streak:{prefix}"
    perfect_key = f"quiz_perfect_awarded:{prefix}"
    return playlist_key, index_key, score_key, correct_key, breakdown_key, streak_key, perfect_key, user_id_str


def _append_score_breakdown(breakdown_key: str, event: dict):
    """Ajoute un événement de score dans la liste stockée en session."""
    try:
        history = session.get(breakdown_key)
        if not isinstance(history, list):
            history = []
        history.append(event)
        session[breakdown_key] = history
    except Exception as exc:
        print(f"[QUIZ SCORE] Impossible d'ajouter le breakdown: {exc}")


def _get_user_double_click_preference() -> bool:
    try:
        if getattr(g, 'current_user', None):
            prefs = g.current_user.get_preferences()
            if 'double_click_validation' in prefs:
                return bool(prefs.get('double_click_validation'))
    except Exception:
        pass
    return True


def _viewer_has_private_access_for_rule_set(rule_set: QuizRuleSet) -> bool:
    """Retourne True si le viewer actuel peut jouer un quiz non-public en incluant les questions privées du créateur.

    - Créateur connecté: OK
    - Autre joueur: OK uniquement si la session contient une autorisation suite à un lien partagé
    """
    try:
        user = getattr(g, 'current_user', None)
        if user and rule_set and rule_set.created_by_user_id == user.id:
            return True
        access = session.get('quiz_private_access')
        if isinstance(access, dict) and rule_set and rule_set.slug:
            return bool(access.get(rule_set.slug))
    except Exception:
        return False
    return False


def _calculate_score(rule_set, question, is_correct):
    """Calcule le score de la question et retourne le détail du calcul."""
    breakdown = {
        'type': 'question',
        'question_id': question.id if question else None,
        'question_label': (question.question_text[:120] + '…') if (question and question.question_text and len(question.question_text) > 120) else (question.question_text if question else ''),
        'difficulty': question.difficulty_level if question else None,
        'was_correct': bool(is_correct),
        'base_points': rule_set.scoring_base_points if rule_set and rule_set.scoring_base_points is not None else 0,
        'difficulty_bonus': 0,
        'difficulty_multiplier': 1.0,
        'question_points': 0,
        'combo_bonus': 0,
        'total_awarded': 0,
        'combo_streak': 0,
        'question_index': None,
    }

    if not rule_set or not is_correct:
        return 0, breakdown

    base_points = breakdown['base_points']
    points = base_points

    if rule_set.scoring_difficulty_bonus_type == 'add':
        bonus_map = rule_set.get_difficulty_bonus_map()
        bonus = bonus_map.get(str(question.difficulty_level), 0) if question else 0
        breakdown['difficulty_bonus'] = bonus
        points += bonus
    elif rule_set.scoring_difficulty_bonus_type == 'mult':
        coeff_map = rule_set.get_difficulty_bonus_map()
        coeff = coeff_map.get(str(question.difficulty_level), 1.0) if question else 1.0
        try:
            coeff = float(coeff)
        except (TypeError, ValueError):
            coeff = 1.0
        points = int(round(base_points * coeff))
        breakdown['difficulty_multiplier'] = coeff
        breakdown['difficulty_bonus'] = points - base_points

    breakdown['question_points'] = int(points)
    breakdown['total_awarded'] = int(points)

    return int(points), breakdown


def next_quiz_question():
    """Retourne la prochaine question du quiz en consommant une playlist pré-générée.
    Si aucune playlist n'existe encore pour ce set, la génère et la stocke en session.
    """
    try:
        params = request.args
        rule_set_slug = (params.get('rule_set') or '').strip()
        history_raw = (params.get('history') or '').strip()
        quick_double_click_param = params.get('quick_double_click')
        if quick_double_click_param is not None:
            quick_double_click = quick_double_click_param.lower() == 'true'
            session['quick_double_click_enabled'] = quick_double_click
        elif 'quick_double_click_enabled' in session:
            quick_double_click = bool(session.get('quick_double_click_enabled'))
        else:
            quick_double_click = _get_user_double_click_preference()
            session['quick_double_click_enabled'] = quick_double_click
        history_ids = []
        if history_raw:
            for token in history_raw.split(','):
                token = token.strip()
                if token.isdigit():
                    history_ids.append(int(token))

        rule_set = None
        playlist_session_key = playlist_index_key = score_session_key = correct_answers_session_key = breakdown_session_key = streak_session_key = perfect_session_key = user_ns = None
        if rule_set_slug:
            rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

        question = None
        total_questions = 0
        if rule_set:
            (
                playlist_session_key,
                playlist_index_key,
                score_session_key,
                correct_answers_session_key,
                breakdown_session_key,
                streak_session_key,
                perfect_session_key,
                user_ns,
            ) = _quiz_session_keys(rule_set.slug)

        question = None
        total_questions = 0
        if rule_set:
            # Si pas encore de playlist, la générer
            playlist: list[int] = session.get(playlist_session_key) or []
            # Si démarrage d'une nouvelle partie (history vide) OU playlist absente, régénérer
            if (not history_raw) or (not playlist):
                viewer_has_private_access = _viewer_has_private_access_for_rule_set(rule_set)
                playlist = _generate_quiz_playlist(
                    rule_set,
                    g.current_user.id if getattr(g, 'current_user', None) else None,
                    viewer_has_private_access=viewer_has_private_access
                )
                session[playlist_session_key] = playlist
                session[playlist_index_key] = 0
                # Reset score/correct pour ce namespace utilisateur+set
                session[score_session_key] = 0
                session[correct_answers_session_key] = 0
                if breakdown_session_key:
                    session[breakdown_session_key] = []
                if streak_session_key:
                    session[streak_session_key] = 0
                if perfect_session_key:
                    session[perfect_session_key] = False
                print(f"[QUIZ PLAYLIST] Générée (reset={not bool(history_raw)}) pour user={user_ns} set='{rule_set.slug}' (len={len(playlist)}): {playlist}")

                # Démarrer une UserQuizSession si utilisateur connecté
                if getattr(g, 'current_user', None):
                    try:
                        # Clore toute session précédente en cours pour ce set
                        prev = (UserQuizSession.query
                                .filter_by(user_id=g.current_user.id, rule_set_id=rule_set.id, status='in_progress')
                                .all())
                        for s in prev:
                            print(f"[QUIZ SESSION] Abandon in-progress session {s.id} for rule_set {s.rule_set_id} before starting new session (user={s.user_id})")
                            s.status = 'abandoned'
                            s.updated_at = datetime.utcnow()
                        # Créer une nouvelle session
                        new_session = UserQuizSession(
                            user_id=g.current_user.id,
                            rule_set_id=rule_set.id,
                            status='in_progress',
                            total_questions=len(playlist),
                            answered_count=0,
                            correct_count=0,
                            total_score=0
                        )
                        db.session.add(new_session)
                        db.session.commit()
                        print(f"[QUIZ SESSION] Started new session {new_session.id} for rule_set {rule_set.id} (user={new_session.user_id}, total_questions={new_session.total_questions})")
                        # Stocker l'ID de session dans la session Flask pour ce namespace utilisateur+set
                        session_key_session_id = f"quiz_session_id:{user_ns}:{rule_set.slug}"
                        session[session_key_session_id] = new_session.id
                        print(f"[QUIZ SESSION] Stored session id in flask session under key='{session_key_session_id}' -> {new_session.id}")
                    except Exception:
                        db.session.rollback()

            total_questions = len(playlist)
            index = int(session.get(playlist_index_key, 0) or 0)

            # Si terminé: fin du quiz
            if index >= total_questions:
                # Récupérer le nombre de bonnes réponses depuis la session
                total_correct_answers = int(session.get(correct_answers_session_key, 0) or 0)
                total_score = int(session.get(score_session_key, 0) or 0)
                total_questions = len(playlist)

                perfect_bonus_added = False
                perfect_bonus_value = 0
                if rule_set and rule_set.perfect_quiz_bonus and perfect_session_key:
                    perfect_bonus_value = int(rule_set.perfect_quiz_bonus or 0)
                    is_perfect = total_questions > 0 and total_correct_answers == total_questions
                    already_awarded = bool(session.get(perfect_session_key))
                    if is_perfect and perfect_bonus_value > 0 and not already_awarded:
                        total_score += perfect_bonus_value
                        session[score_session_key] = total_score
                        session[perfect_session_key] = True
                        perfect_bonus_added = True
                        if breakdown_session_key:
                            bonus_event = {
                                'type': 'perfect_bonus',
                                'label': 'Bonus quiz parfait',
                                'value': perfect_bonus_value,
                                'total_awarded': perfect_bonus_value,
                            }
                            _append_score_breakdown(breakdown_session_key, bonus_event)
                score_breakdown = list(session.get(breakdown_session_key, [])) if breakdown_session_key else []

                # Clore la UserQuizSession comme completed si présente
                if getattr(g, 'current_user', None):
                    try:
                        session_key_session_id = f"quiz_session_id:{user_ns}:{rule_set.slug}"
                        sess_id = session.get(session_key_session_id)
                        if not sess_id:
                            print(f"[QUIZ SESSION] No session id found in flask session for key='{session_key_session_id}' during quiz completion.")
                        if sess_id:
                            s = UserQuizSession.query.get(sess_id)
                            if s and s.status == 'in_progress':
                                print(
                                    f"[QUIZ SESSION] Updating session {s.id} (user={s.user_id}) before marking completed: "
                                    f"answered={s.answered_count}, total={s.total_questions}, correct={s.correct_count}, score={s.total_score}"
                                )
                                s.status = 'completed'
                                s.answered_count = s.total_questions
                                s.correct_count = total_correct_answers
                                s.total_score = total_score
                                s.updated_at = datetime.utcnow()
                                db.session.commit()
                                print(
                                    f"[QUIZ SESSION] Session {s.id} marked completed at quiz end: "
                                    f"answered={s.answered_count}, correct={s.correct_count}, score={s.total_score}"
                                )
                            else:
                                print(f"[QUIZ SESSION] Expected in-progress session for sess_id={sess_id}, found status={s.status if s else 'missing'} (user={g.current_user.id}).")
                    except Exception:
                        db.session.rollback()

                # Si perfect bonus obtenu, afficher l'animation d'abord
                if perfect_bonus_added:
                    return render_template(
                        'quiz_perfect_animation.html',
                        rule_set=rule_set,
                        total_questions=total_questions,
                        total_correct_answers=total_correct_answers,
                        perfect_bonus_value=perfect_bonus_value,
                        history=history_raw or ''
                    )

                rule_set_stats = None
                if rule_set:
                    user_id = g.current_user.id if getattr(g, 'current_user', None) and g.current_user.is_authenticated else None
                    rule_set_stats = get_rule_set_stats(rule_set, user_id, viewer_has_private_access=_viewer_has_private_access_for_rule_set(rule_set))

                return render_template(
                    'quiz_final.html',
                    rule_set=rule_set,
                    rule_set_stats=rule_set_stats,
                    total_questions=total_questions,
                    total_score=total_score,
                    total_correct_answers=total_correct_answers,
                    perfect_bonus_added=perfect_bonus_added,
                    perfect_bonus_value=perfect_bonus_value,
                    score_breakdown=score_breakdown,
                    history=history_raw or '',
                    quick_double_click=quick_double_click
                )

            # Charger la prochaine question via l'ID de la playlist
            next_question_id = playlist[index]
            question = Question.query.options(
                db.joinedload(Question.images),
                db.joinedload(Question.detailed_answer_image),
                db.joinedload(Question.answer_image_links).joinedload(AnswerImageLink.image)
            ).get(next_question_id)
        else:
            # Mode sans set explicite: fallback à l'aléatoire historique (comme avant)
            query = Question.query.filter(Question.is_published.is_(True), Question.is_private.is_(False))
            query = _apply_quiz_filters(query, params)
            if history_ids:
                query = query.filter(~Question.id.in_(history_ids))
            question = query.options(
                db.joinedload(Question.images),
                db.joinedload(Question.detailed_answer_image),
                db.joinedload(Question.answer_image_links).joinedload(AnswerImageLink.image)
            ).order_by(db.func.random()).first()

        # Si on sort du mode set (pas de rule_set), marquer toute session in_progress comme abandonnée
        if not rule_set and getattr(g, 'current_user', None):
            try:
                # Abandonner toutes sessions en cours (tous sets) si l'utilisateur a quitté le set
                in_prog = UserQuizSession.query.filter_by(user_id=g.current_user.id, status='in_progress').all()
                for s in in_prog:
                    print(f"[QUIZ SESSION] Abandon session {s.id} after leaving rule_set context in /api/quiz/next (user={s.user_id})")
                    s.status = 'abandoned'
                    s.updated_at = datetime.utcnow()
                if in_prog:
                    db.session.commit()
            except Exception:
                db.session.rollback()

        # Debug logging
        print(f"[QUIZ NEXT] Rule set: {rule_set_slug}, History: {history_raw}")
        print(f"[QUIZ NEXT] Selected question ID: {question.id if question else 'None'}")
        print(f"[QUIZ NEXT] Question difficulty: {question.difficulty_level if question else 'N/A'}")

        # Calculer la progression et le score total (stocké en session)
        total_score = 0
        current_question_num = 0

        if rule_set:
            # Gestion du score en session (reset en début de session)
            if not history_raw:
                # Note: la playlist réinitialise déjà score/correct au moment de la génération
                session[score_session_key] = session.get(score_session_key, 0) or 0
                session[correct_answers_session_key] = session.get(correct_answers_session_key, 0) or 0
            total_score = int(session.get(score_session_key, 0) or 0)

            # Progression basée sur la playlist
            playlist = session.get(playlist_session_key) or []
            index = int(session.get(playlist_index_key, 0) or 0)
            # Affichage utilisateur: index courant (1-based)
            current_question_num = min(index + 1, len(playlist)) if playlist else 1
            total_questions = len(playlist)

        # Mélanger les propositions de réponses pour éviter que la bonne réponse soit toujours à la même position
        if question and question.possible_answers:
            try:
                original_answers = question.possible_answers.split('|||')
                num_answers = len(original_answers)

                # Vérifications de sécurité
                if num_answers == 0:
                    print(f"[QUIZ SHUFFLE] Question {question.id} has no answers, skipping shuffle")
                    return

                # Convertir correct_answer en int si c'est une chaîne
                try:
                    correct_answer_int = int(question.correct_answer)
                    if correct_answer_int < 1 or correct_answer_int > num_answers:
                        print(f"[QUIZ SHUFFLE] Question {question.id} has invalid correct_answer: {question.correct_answer} (should be 1-{num_answers}), skipping shuffle")
                        return
                    else:
                        question.correct_answer = correct_answer_int  # Mettre à jour pour être sûr
                except (ValueError, TypeError):
                    print(f"[QUIZ SHUFFLE] Question {question.id} has invalid correct_answer type: {type(question.correct_answer)} value: {question.correct_answer}, skipping shuffle")
                    return

                # Créer une liste d'indices [0, 1, 2, ...] et la mélanger
                answer_indices = list(range(num_answers))
                random.shuffle(answer_indices)

                # Créer les réponses dans l'ordre mélangé
                shuffled_answers = [original_answers[i] for i in answer_indices]

                # Stocker l'ordre de mélange en session pour cette question (clé par question_id)
                shuffle_key = f"question_shuffle_{question.id}"
                session[shuffle_key] = answer_indices

                # Remplacer temporairement les réponses dans l'objet question pour le template
                question._shuffled_answers = shuffled_answers

                # Calculer la nouvelle position de la bonne réponse (1-based pour correspondre à correct_answer)
                original_correct_index = question.correct_answer - 1  # 0-based
                new_correct_position = answer_indices.index(original_correct_index) + 1  # 1-based
                question._shuffled_correct_answer = new_correct_position

                # Calculer les indices originaux pour chaque position mélangée (pour les images)
                question._original_indices = answer_indices

                print(f"[QUIZ SHUFFLE] Question {question.id}: shuffled {num_answers} answers, correct answer moved from position {question.correct_answer} to {new_correct_position}")
            except Exception as e:
                print(f"[QUIZ SHUFFLE] Error shuffling answers for question {question.id}: {str(e)}, skipping shuffle")
                # En cas d'erreur, on continue sans mélanger

        return render_template('quiz_question.html',
                             question=question,
                             history=history_raw,
                             rule_set=rule_set,
                             current_question_num=current_question_num,
                             total_questions=total_questions,
                             total_score=total_score,
                             quick_double_click=quick_double_click)
    except Exception as e:
        error_msg = str(e).encode('ascii', 'ignore').decode('ascii')
        print(f"[QUIZ NEXT] ERREUR dans next_quiz_question: {error_msg}")
        import traceback
        traceback.print_exc()
        return f"Erreur: {error_msg}", 400


def show_quiz_final():
    """Affiche le récapitulatif final du quiz (utilisé après l'animation perfect)."""
    try:
        params = request.args
        rule_set_slug = (params.get('rule_set') or '').strip()
        history_raw = (params.get('history') or '').strip()

        rule_set = None
        if rule_set_slug:
            rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()

        if not rule_set:
            return "Set de règles introuvable", 404

        (
            playlist_session_key,
            playlist_index_key,
            score_session_key,
            correct_answers_session_key,
            breakdown_session_key,
            streak_session_key,
            perfect_session_key,
            user_ns,
        ) = _quiz_session_keys(rule_set.slug)

        total_correct_answers = int(session.get(correct_answers_session_key, 0) or 0)
        total_score = int(session.get(score_session_key, 0) or 0)
        playlist = session.get(playlist_session_key) or []
        total_questions = len(playlist)
        score_breakdown = list(session.get(breakdown_session_key, [])) if breakdown_session_key else []
        perfect_bonus_added = bool(session.get(perfect_session_key))
        perfect_bonus_value = int(rule_set.perfect_quiz_bonus or 0) if perfect_bonus_added else 0

        quick_double_click = bool(session.get('quick_double_click_enabled', False))

        rule_set_stats = None
        if rule_set:
            user_id = g.current_user.id if getattr(g, 'current_user', None) and g.current_user.is_authenticated else None
            rule_set_stats = get_rule_set_stats(rule_set, user_id, viewer_has_private_access=_viewer_has_private_access_for_rule_set(rule_set))

        return render_template(
            'quiz_final.html',
            rule_set=rule_set,
            rule_set_stats=rule_set_stats,
            total_questions=total_questions,
            total_score=total_score,
            total_correct_answers=total_correct_answers,
            perfect_bonus_added=perfect_bonus_added,
            perfect_bonus_value=perfect_bonus_value,
            score_breakdown=score_breakdown,
            history=history_raw or '',
            quick_double_click=quick_double_click
        )
    except Exception as e:
        error_msg = str(e).encode('ascii', 'ignore').decode('ascii')
        return f"Erreur: {error_msg}", 400


def cancel_quiz_session():
    """Marque la session de quiz en cours comme abandonnée pour l'utilisateur connecté et le set fourni."""
    try:
        if not getattr(g, 'current_user', None):
            return "Non connecté", 401
        rule_set_slug = (request.form.get('rule_set') or '').strip()
        if not rule_set_slug:
            return "Paramètre 'rule_set' manquant", 400
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
        if not rule_set:
            return "Set inconnu", 404
        _, _, _, _, _, _, _, user_ns = _quiz_session_keys(rule_set.slug)
        session_key_session_id = f"quiz_session_id:{user_ns}:{rule_set.slug}"
        sess_id = session.get(session_key_session_id)
        if not sess_id:
            return "Aucune session en cours", 200
        s = UserQuizSession.query.get(sess_id)
        if s and s.status == 'in_progress':
            print(f"[QUIZ SESSION] Cancel request abandoning session {s.id} for rule_set {rule_set.id} (user={s.user_id})")
            s.status = 'abandoned'
            s.updated_at = datetime.utcnow()
            db.session.commit()
        return "OK", 200
    except Exception as e:
        db.session.rollback()
        return { 'error': str(e) }, 400


def submit_quiz_answer():
    """Valider la réponse de l'utilisateur, mettre à jour les stats et retourner le résultat."""
    try:
        question_id_raw = (request.form.get('question_id') or '').strip()
        selected_answer = (request.form.get('selected_answer') or '').strip()
        history_raw = (request.form.get('history') or '').strip()
        rule_set_slug = (request.form.get('rule_set') or '').strip()
        is_timeout = bool((request.form.get('timeout') or '').strip())
        quick_double_click_raw = request.form.get('quick_double_click')
        if quick_double_click_raw is not None:
            quick_double_click = quick_double_click_raw.strip().lower() == 'true'
            session['quick_double_click_enabled'] = quick_double_click
        elif 'quick_double_click_enabled' in session:
            quick_double_click = bool(session.get('quick_double_click_enabled'))
        else:
            quick_double_click = _get_user_double_click_preference()
            session['quick_double_click_enabled'] = quick_double_click

        if not question_id_raw.isdigit():
            return "Identifiant de question invalide", 400

        question = Question.query.options(
            db.joinedload(Question.images),
            db.joinedload(Question.detailed_answer_image),
            db.joinedload(Question.answer_image_links).joinedload(AnswerImageLink.image)
        ).get_or_404(int(question_id_raw))

        # Vérifier si les réponses ont été mélangées pour cette question
        shuffle_key = f"question_shuffle_{question.id}"
        shuffle_order = session.get(shuffle_key)

        if shuffle_order and selected_answer and selected_answer.isdigit():
            # Convertir l'index sélectionné (dans l'ordre mélangé, 1-based) vers l'index original (1-based)
            selected_index_mixed = int(selected_answer) - 1  # 0-based
            original_index = shuffle_order[selected_index_mixed] + 1  # 1-based
            selected_answer_original = str(original_index)
        else:
            selected_answer_original = selected_answer

        correct_value = (question.correct_answer or '').strip()
        # Si pas de réponse (timer expiré ou non sélection), considérer comme faux
        is_correct = bool(selected_answer_original) and (selected_answer_original == correct_value)

        # Debug logging
        print(f"[QUIZ ANSWER] Question ID: {question_id_raw}, Selected: '{selected_answer}', Correct: '{correct_value}', Is correct: {is_correct}")

        # Charger le set de règles si spécifié
        rule_set = None
        playlist_session_key = playlist_index_key = score_session_key = correct_answers_session_key = breakdown_session_key = streak_session_key = perfect_session_key = user_ns = None
        if rule_set_slug:
            rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
            if rule_set:
                (
                    playlist_session_key,
                    playlist_index_key,
                    score_session_key,
                    correct_answers_session_key,
                    breakdown_session_key,
                    streak_session_key,
                    perfect_session_key,
                    user_ns,
                ) = _quiz_session_keys(rule_set.slug)

        # Calculer le score selon les règles
        score = 0
        breakdown = None
        combo_triggered = False
        combo_bonus = 0
        combo_streak = 0
        if rule_set:
            history_ids = []
            if history_raw:
                for token in history_raw.split(','):
                    token = token.strip()
                    if token.isdigit():
                        history_ids.append(int(token))
            question_index = len(history_ids) + 1
            question_score, breakdown = _calculate_score(rule_set, question, is_correct)

            streak_after = 0
            if rule_set.combo_bonus_enabled and rule_set.combo_step and rule_set.combo_bonus_points:
                combo_step = max(int(rule_set.combo_step), 0)
                combo_points = int(rule_set.combo_bonus_points or 0)
                current_streak = int(session.get(streak_session_key, 0) or 0) if streak_session_key else 0
                if is_correct and combo_step > 0 and combo_points > 0:
                    current_streak += 1
                    if current_streak % combo_step == 0:
                        combo_bonus = combo_points
                        combo_triggered = True
                else:
                    current_streak = 0
                streak_after = current_streak
                combo_streak = streak_after
                if streak_session_key:
                    session[streak_session_key] = current_streak
            else:
                if streak_session_key:
                    session[streak_session_key] = 0

            if breakdown:
                breakdown['question_index'] = question_index
                breakdown['combo_bonus'] = combo_bonus
                breakdown['combo_triggered'] = combo_triggered
                breakdown['combo_streak'] = streak_after
                breakdown['total_awarded'] = int(breakdown.get('question_points', 0) + combo_bonus)
                score = breakdown['total_awarded']
            else:
                score = question_score + combo_bonus

            if breakdown_session_key and breakdown:
                _append_score_breakdown(breakdown_session_key, breakdown)

        # Mettre à jour les statistiques globales de la question
        question.times_answered = (question.times_answered or 0) + 1
        if is_correct:
            question.success_count = (question.success_count or 0) + 1
        question.updated_at = datetime.utcnow()

        # Mettre à jour les statistiques utilisateur-question
        if getattr(g, 'current_user', None):
            stat = UserQuestionStat.query.filter_by(user_id=g.current_user.id, question_id=question.id).first()
            if not stat:
                stat = UserQuestionStat(user_id=g.current_user.id, question_id=question.id)
                db.session.add(stat)
            stat.times_answered = (stat.times_answered or 0) + 1
            if is_correct:
                stat.success_count = (stat.success_count or 0) + 1
            stat.last_selected_answer = selected_answer_original
            stat.last_is_correct = is_correct
            stat.last_answered_at = datetime.utcnow()

        # Mettre à jour la distribution des réponses (QuestionAnswerStat)
        try:
            if selected_answer_original and selected_answer_original.isdigit():
                idx = int(selected_answer_original)
                qa = QuestionAnswerStat.query.filter_by(question_id=question.id, answer_index=idx).first()
                if not qa:
                    qa = QuestionAnswerStat(question_id=question.id, answer_index=idx, selected_count=0)
                    db.session.add(qa)
                qa.selected_count = (qa.selected_count or 0) + 1
        except Exception:
            # Ne pas bloquer la réponse si l'agg échoue
            db.session.rollback()

        db.session.commit()

        # Mettre à jour le score total et le nombre de bonnes réponses en session (namespace user)
        if rule_set and score_session_key and correct_answers_session_key:
            total_score_session = int(session.get(score_session_key, 0) or 0)
            if score:
                total_score_session += int(score)
            session[score_session_key] = total_score_session

            # Compter les bonnes réponses
            total_correct_answers_session = int(session.get(correct_answers_session_key, 0) or 0)
            if is_correct:
                total_correct_answers_session += 1
            session[correct_answers_session_key] = total_correct_answers_session

        # Mettre à jour la progression de playlist (si set de règles, namespace user)
        if rule_set and playlist_session_key and playlist_index_key:
            index = int(session.get(playlist_index_key, 0) or 0)
            playlist = session.get(playlist_session_key) or []
            # Avancer l'index si la question correspond à l'élément courant
            if index < len(playlist) and playlist[index] == question.id:
                session[playlist_index_key] = index + 1

            # Mettre à jour la UserQuizSession si présente
            if getattr(g, 'current_user', None):
                try:
                    session_key_session_id = f"quiz_session_id:{user_ns}:{rule_set.slug}"
                    sess_id = session.get(session_key_session_id)
                    if not sess_id:
                        print(f"[QUIZ SESSION] No session id found in flask session for key='{session_key_session_id}' during answer update.")
                    if sess_id:
                        s = UserQuizSession.query.get(sess_id)
                        if s and s.status == 'in_progress':
                            before_answered = s.answered_count or 0
                            before_correct = s.correct_count or 0
                            before_score = s.total_score or 0
                            print(
                                f"[QUIZ SESSION] Answer update for session {s.id} (user={s.user_id}): "
                                f"answered={before_answered}, total={s.total_questions}, correct={before_correct}, score={before_score}"
                            )
                            s.answered_count = min((s.answered_count or 0) + 1, s.total_questions or 0)
                            if is_correct:
                                s.correct_count = (s.correct_count or 0) + 1
                            # total_score est déjà mis à jour en session; l'appliquer si on a un score crédité
                            if score:
                                s.total_score = (s.total_score or 0) + int(score)
                            if (s.total_questions or 0) > 0 and s.answered_count >= (s.total_questions or 0):
                                s.status = 'completed'
                                print(f"[QUIZ SESSION] Session {s.id} reached completion via answer handler.")
                            s.updated_at = datetime.utcnow()
                            db.session.commit()
                            print(
                                f"[QUIZ SESSION] Post-answer session {s.id}: "
                                f"status={s.status}, answered={s.answered_count}, correct={s.correct_count}, score={s.total_score}"
                            )
                        else:
                            print(f"[QUIZ SESSION] Retrieved session {getattr(s, 'id', None)} but status={getattr(s, 'status', None)} during answer update (expected in_progress).")
                except Exception:
                    db.session.rollback()

        # Mettre à jour l'historique côté client (ajouter la question actuelle)
        history_ids = []
        if history_raw:
            for token in history_raw.split(','):
                token = token.strip()
                if token.isdigit():
                    history_ids.append(int(token))
        if question.id not in history_ids:
            history_ids.append(question.id)
        next_history = ','.join(str(i) for i in history_ids)

        # Calculer la progression et le score total mis à jour
        total_questions = 0
        current_question_num = 0
        total_score = 0

        if rule_set:
            # Progression basée sur la playlist
            (
                playlist_session_key,
                playlist_index_key,
                score_session_key,
                correct_answers_session_key,
                breakdown_session_key,
                streak_session_key,
                perfect_session_key,
                user_ns,
            ) = _quiz_session_keys(rule_set.slug)
            index = int(session.get(playlist_index_key, 0) or 0)
            playlist = session.get(playlist_session_key) or []
            total_questions = len(playlist)
            current_question_num = min(index, total_questions)

            # Score total depuis la session
            score_session_key = score_session_key
            total_score = int(session.get(score_session_key, 0) or 0)

        return render_template(
            'quiz_result.html',
            question=question,
            is_correct=is_correct,
            selected=selected_answer_original,
            history=next_history,
            rule_set=rule_set,
            score=score,
            combo_triggered=combo_triggered,
            combo_bonus=combo_bonus,
            combo_streak=combo_streak,
            current_question_num=current_question_num,
            total_questions=total_questions,
            total_score=total_score,
            is_timeout=is_timeout,
            quick_double_click=quick_double_click
        )
    except Exception as e:
        error_msg = str(e).encode('ascii', 'ignore').decode('ascii')
        return f"Erreur: {error_msg}", 400
