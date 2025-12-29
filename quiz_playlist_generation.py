import random
from models import db, QuizRuleSet, Question, UserQuestionStat, Country


def _public_questions_query():
    """Pool public strict: uniquement questions publiées et non privées."""
    return Question.query.filter(Question.is_published.is_(True), Question.is_private.is_(False))


def _base_questions_for_rule_set(rule_set: QuizRuleSet, current_user_id: int | None, viewer_has_private_access: bool = False):
    """Requête de base du pool de questions pour un rule_set et un joueur donné.

    - Quiz public: seulement pool public.
    - Quiz privé/pending/rejected: si accès privé accordé (créateur OU lien partagé), inclure les questions du créateur (même privées/non publiées).
    - Respecte `rule_set.question_pool_scope` ('all'|'mine').
    """
    if not rule_set:
        return _public_questions_query()

    creator_id = int(rule_set.created_by_user_id)
    is_public_quiz = getattr(rule_set, 'visibility_status', 'public') == 'public'
    scope = getattr(rule_set, 'question_pool_scope', 'all') or 'all'
    scope = 'mine' if str(scope).lower() == 'mine' else 'all'

    if scope == 'mine':
        base = Question.query.filter(Question.author_id == creator_id)
        # Si quiz public OU accès privé non accordé, ne jamais exposer des questions non publiées/non validées
        if is_public_quiz or not viewer_has_private_access:
            base = base.filter(Question.is_published.is_(True), Question.is_private.is_(False))
        return base

    # scope == 'all'
    base = _public_questions_query()
    if (not is_public_quiz) and viewer_has_private_access:
        base = Question.query.filter(
            db.or_(
                db.and_(Question.is_published.is_(True), Question.is_private.is_(False)),
                Question.author_id == creator_id,
            )
        )
    return base


def _apply_rule_set_filters(query, rule_set: QuizRuleSet):
    """Applique les filtres d'un rule_set (thèmes/pays/difficultés) à une requête de questions."""
    if not rule_set:
        return query

    allowed_diffs = rule_set.get_allowed_difficulties()
    if allowed_diffs:
        query = query.filter(Question.difficulty_level.in_(allowed_diffs))

    if not rule_set.use_all_broad_themes and rule_set.allowed_broad_themes:
        theme_ids = [t.id for t in rule_set.allowed_broad_themes]
        query = query.filter(Question.broad_theme_id.in_(theme_ids))

    if not rule_set.use_all_specific_themes and rule_set.allowed_specific_themes:
        sub_theme_ids = [st.id for st in rule_set.allowed_specific_themes]
        query = query.filter(Question.specific_theme_id.in_(sub_theme_ids))

    if not rule_set.use_all_countries:
        c_ids = [c.id for c in (rule_set.allowed_countries or [])]
        if c_ids:
            query = query.filter(Question.countries.any(Country.id.in_(c_ids)))
        else:
            query = query.filter(~Question.countries.any())

    return query


def _apply_quiz_filters(query, params):
    """Appliquer les filtres du quiz (thèmes, pays, difficulté) au query de base."""
    rule_set_slug = (params.get('rule_set') or '').strip()
    if rule_set_slug:
        # Appliquer les règles du set
        rule_set = QuizRuleSet.query.filter_by(slug=rule_set_slug, is_active=True).first()
        if rule_set:
            # Difficultés autorisées
            allowed_diffs = rule_set.get_allowed_difficulties()
            if allowed_diffs:
                query = query.filter(Question.difficulty_level.in_(allowed_diffs))

            # Thèmes larges
            if not rule_set.use_all_broad_themes and rule_set.allowed_broad_themes:
                theme_ids = [t.id for t in rule_set.allowed_broad_themes]
                query = query.filter(Question.broad_theme_id.in_(theme_ids))

            # Sous-thèmes
            if not rule_set.use_all_specific_themes and rule_set.allowed_specific_themes:
                sub_theme_ids = [st.id for st in rule_set.allowed_specific_themes]
                query = query.filter(Question.specific_theme_id.in_(sub_theme_ids))

            # Pays
            if not rule_set.use_all_countries:
                c_ids = [c.id for c in (rule_set.allowed_countries or [])]
                if c_ids:
                    query = query.filter(Question.countries.any(Country.id.in_(c_ids)))
                else:
                    query = query.filter(~Question.countries.any())
    else:
        # Mode manuel - appliquer les filtres classiques
        broad_theme_id = (params.get('broad_theme_id') or '').strip()
        if broad_theme_id.isdigit():
            query = query.filter(Question.broad_theme_id == int(broad_theme_id))

        specific_theme_id = (params.get('specific_theme_id') or '').strip()
        if specific_theme_id.isdigit():
            query = query.filter(Question.specific_theme_id == int(specific_theme_id))

        country_id = (params.get('country_id') or '').strip()
        if country_id.isdigit():
            query = query.filter(Question.countries.any(Country.id == int(country_id)))

        difficulty_level = (params.get('difficulty_level') or '').strip()
        if difficulty_level.isdigit():
            query = query.filter(Question.difficulty_level == int(difficulty_level))

    return query


def get_rule_set_stats(rule_set: QuizRuleSet, user_id: int | None, viewer_has_private_access: bool = False) -> dict:
    """
    Calcule les statistiques du pool de questions pour un rule_set donné.
    Retourne: {
        'total_pool': int,
        'questions_per_game': int,
        'user_seen_count': int, # Seulement si user_id fourni
        'freshness': str # 'new', 'mixed', 'all_seen', 'unknown'
    }
    """
    stats = {
        'total_pool': 0,
        'questions_per_game': 0,
        'user_seen_count': 0,
        'freshness': 'unknown'
    }

    if not rule_set:
        return stats

    # 1. Calculer le nombre de questions par partie
    if rule_set.question_selection_mode == 'manual':
        stats['questions_per_game'] = len(rule_set.selected_questions)
        # Pour le mode manuel, le pool EST la sélection
        is_public_quiz = getattr(rule_set, 'visibility_status', 'public') == 'public'
        creator_id = int(rule_set.created_by_user_id)
        if (not is_public_quiz) and viewer_has_private_access:
            pool_ids = [q.id for q in rule_set.selected_questions if (q.author_id == creator_id) or (q.is_published and not q.is_private)]
        else:
            pool_ids = [q.id for q in rule_set.selected_questions if (q.is_published and not q.is_private)]
        pool_query = Question.query.filter(Question.id.in_(pool_ids))
    else:
        qmap = rule_set.get_questions_per_difficulty()
        stats['questions_per_game'] = sum(int(v) for v in qmap.values() if v)
        
        # 2. Construire la requête du pool
        pool_query = _apply_rule_set_filters(_base_questions_for_rule_set(rule_set, user_id, viewer_has_private_access=viewer_has_private_access), rule_set)

    # Compter le pool total
    stats['total_pool'] = pool_query.count()

    # 3. Stats utilisateur
    if user_id:
        # Récupérer les IDs du pool
        pool_ids = [r.id for r in pool_query.with_entities(Question.id).all()]
        
        if pool_ids:
            seen_count = UserQuestionStat.query.filter(
                UserQuestionStat.user_id == user_id,
                UserQuestionStat.question_id.in_(pool_ids)
            ).count()
            stats['user_seen_count'] = seen_count
            
            unseen_count = stats['total_pool'] - seen_count
            
            if unseen_count == 0:
                stats['freshness'] = 'all_seen'
            elif unseen_count >= stats['questions_per_game']:
                stats['freshness'] = 'new'
            else:
                stats['freshness'] = 'mixed'
    
    return stats


def _interleave_round_robin(lists_by_difficulty):
    """Intercale les listes de questions par difficulté (round-robin) pour varier l'ordre.
    Entrée: dict[int,list[int]]
    Sortie: list[int]
    """
    # Convertir en liste de listes en conservant un ordre stable des clés
    difficulties = sorted(lists_by_difficulty.keys())
    buckets = [list(lists_by_difficulty[d]) for d in difficulties if lists_by_difficulty.get(d)]
    result = []
    # Tant qu'il reste des éléments dans au moins un bucket
    while any(buckets):
        next_buckets = []
        for bucket in buckets:
            if bucket:
                result.append(bucket.pop(0))
            # garder le bucket s'il reste des éléments
            if bucket:
                next_buckets.append(bucket)
        buckets = next_buckets
    return result


def _get_user_answered_keywords(user_id: int) -> set[int]:
    """Récupère les IDs de tous les keywords déjà répondus par l'utilisateur."""
    if not user_id:
        return set()

    try:
        # Récupérer toutes les questions déjà répondues
        answered_question_ids = {row.question_id for row in
                                 UserQuestionStat.query.with_entities(UserQuestionStat.question_id)
                                 .filter_by(user_id=user_id).all()}

        if not answered_question_ids:
            return set()

        # Récupérer les keywords de ces questions
        from sqlalchemy import select
        keyword_ids = set()
        result = db.session.execute(
            select(db.literal_column('keyword_id'))
            .select_from(db.text('question_keywords'))
            .where(db.literal_column('question_id').in_(answered_question_ids))
        )
        keyword_ids = {row[0] for row in result}
        return keyword_ids
    except Exception as e:
        print(f"[KEYWORDS] Erreur lors de la récupération des keywords répondus: {e}")
        return set()


def _select_questions_with_keyword_logic(
    candidate_ids: list[int],
    seen_question_ids: set[int],
    used_keywords: set[int],
    answered_keywords: set[int],
    prevent_duplicate_keywords: bool,
    quota: int
) -> tuple[list[int], set[int], dict[str, any]]:
    """
    Sélectionne les questions en respectant la logique des keywords.

    Priorités (par ordre d'importance):
    1. Condition QuizRuleSet (ABSOLU) - déjà appliqué dans candidate_ids
    2. Pas de doublons de keywords dans le quiz (si prevent_duplicate_keywords)
    3. Pas de questions déjà répondues
    4. Pas de keywords déjà répondus

    Retourne: (selected_ids, used_keywords_updated, stats)
    """
    if not candidate_ids or quota <= 0:
        return [], used_keywords, {'perfect': True, 'conditions_met': []}

    # Charger toutes les questions candidates avec leurs keywords
    candidates = Question.query.filter(Question.id.in_(candidate_ids)).options(
        db.joinedload(Question.keywords)
    ).all()

    # Stats pour le debug
    stats = {
        'perfect': True,
        'total_candidates': len(candidates),
        'conditions_met': [],
        'fallback_used': []
    }

    selected_ids = []
    current_used_keywords = set(used_keywords)

    # Fonction pour scorer une question selon les priorités
    def score_question(q: Question) -> tuple:
        """Retourne un tuple de score (plus élevé = meilleur). Format: (prio1, prio2, prio3, prio4)"""
        q_keywords = {kw.id for kw in q.keywords}

        # Priorité 1: Pas de doublons de keywords (si activé)
        if prevent_duplicate_keywords and q_keywords:
            has_duplicate_keyword = bool(q_keywords & current_used_keywords)
        else:
            has_duplicate_keyword = False

        # Priorité 2: Question non répondue
        is_unseen = q.id not in seen_question_ids

        # Priorité 3: Keywords non répondus
        if q_keywords and answered_keywords:
            has_unanswered_keywords = bool(q_keywords & answered_keywords)
        else:
            has_unanswered_keywords = False

        # Questions sans keywords ont un bonus (pas de risque de doublon)
        no_keywords = len(q_keywords) == 0

        # Retourner score (format: pas de doublon keyword, non vue, pas keyword répondu, sans keyword)
        return (
            not has_duplicate_keyword,  # Vrai = 1, Faux = 0 (on veut True en premier)
            is_unseen,
            not has_unanswered_keywords,
            no_keywords
        )

    # Trier les candidats par score (du meilleur au pire)
    sorted_candidates = sorted(candidates, key=score_question, reverse=True)

    # Sélectionner jusqu'au quota
    for q in sorted_candidates:
        if len(selected_ids) >= quota:
            break

        q_keywords = {kw.id for kw in q.keywords}

        # Vérifier si on respecte toutes les conditions
        conditions_perfect = True

        # Condition 2: Pas de doublons de keywords
        if prevent_duplicate_keywords and q_keywords and (q_keywords & current_used_keywords):
            conditions_perfect = False
            stats['fallback_used'].append('keyword_duplicate')

        # Condition 3: Question non répondue
        if q.id in seen_question_ids:
            conditions_perfect = False
            stats['fallback_used'].append('question_already_seen')

        # Condition 4: Keywords non répondus
        if q_keywords and answered_keywords and (q_keywords & answered_keywords):
            conditions_perfect = False
            stats['fallback_used'].append('keyword_already_answered')

        if not conditions_perfect:
            stats['perfect'] = False

        selected_ids.append(q.id)
        current_used_keywords.update(q_keywords)

    # Statistiques finales
    if stats['perfect']:
        stats['conditions_met'] = ['Toutes les conditions respectées OK']
    else:
        fallback_counts = {}
        for fb in stats['fallback_used']:
            fallback_counts[fb] = fallback_counts.get(fb, 0) + 1
        stats['conditions_met'] = [
            f"ATTENTION {count}x {reason.replace('_', ' ')}"
            for reason, count in fallback_counts.items()
        ]

    return selected_ids, current_used_keywords, stats


def _generate_quiz_playlist(rule_set: QuizRuleSet, current_user_id: int | None, viewer_has_private_access: bool = False) -> list[int]:
    """
    Génère la playlist (liste d'IDs de questions) pour un quiz à longueur fixe.

    Priorités de sélection:
    1. Respecter les conditions du QuizRuleSet (ABSOLU)
    2. Éviter les doublons de keywords dans le quiz
    3. Éviter les questions déjà répondues
    4. Éviter les keywords déjà répondus

    En mode 'manual': réordonne la liste sélectionnée en appliquant la logique keywords.
    En mode 'auto': respecte les quotas par difficulté avec gestion keywords.
    """
    try:
        print(f"\n[QUIZ PLAYLIST] === Generation playlist pour {rule_set.name} ===")

        # Récupérer les IDs déjà vus par l'utilisateur (si connecté)
        seen_ids = set()
        answered_keywords = set()
        if current_user_id:
            seen_ids = {row.question_id for row in
                       UserQuestionStat.query.with_entities(UserQuestionStat.question_id)
                       .filter_by(user_id=current_user_id).all()}
            answered_keywords = _get_user_answered_keywords(current_user_id)
            print(f"[QUIZ PLAYLIST] Utilisateur {current_user_id}: {len(seen_ids)} questions vues, {len(answered_keywords)} keywords répondus")

        prevent_duplicate_keywords = rule_set.prevent_duplicate_keywords
        print(f"[QUIZ PLAYLIST] Prévention doublons keywords: {'OUI' if prevent_duplicate_keywords else 'NON'}")

        creator_id = int(rule_set.created_by_user_id)
        is_public_quiz = getattr(rule_set, 'visibility_status', 'public') == 'public'

        # Mode manuel: partir de la sélection explicite
        if rule_set.question_selection_mode == 'manual' and rule_set.selected_questions:
            print(f"[QUIZ PLAYLIST] Mode MANUEL: {len(rule_set.selected_questions)} questions sélectionnées")
            if (not is_public_quiz) and viewer_has_private_access:
                selected = [q for q in rule_set.selected_questions if (q.author_id == creator_id) or (q.is_published and not q.is_private)]
            else:
                selected = [q for q in rule_set.selected_questions if (q.is_published and not q.is_private)]
            candidate_ids = [q.id for q in selected]

            # Appliquer la logique keywords sur toute la sélection
            playlist, _, stats = _select_questions_with_keyword_logic(
                candidate_ids=candidate_ids,
                seen_question_ids=seen_ids,
                used_keywords=set(),
                answered_keywords=answered_keywords,
                prevent_duplicate_keywords=prevent_duplicate_keywords,
                quota=len(candidate_ids)
            )

            # Logs
            if stats['perfect']:
                print(f"[QUIZ PLAYLIST] CONDITIONS PARFAITES: {', '.join(stats['conditions_met'])}")
            else:
                print("[QUIZ PLAYLIST] COMPROMIS NECESSAIRES:")
                for condition in stats['conditions_met']:
                    print(f"[QUIZ PLAYLIST]    {condition}")

            print(f"[QUIZ PLAYLIST] Playlist générée: {len(playlist)} questions")
            return playlist

        # Mode auto: quotas par difficulté et filtres de thèmes
        qmap = rule_set.get_questions_per_difficulty() or {}
        allowed_diffs = rule_set.get_allowed_difficulties() or [1, 2, 3, 4, 5]
        print(f"[QUIZ PLAYLIST] Mode AUTO: difficultés {allowed_diffs}, quotas {qmap}")
        order_mode = getattr(rule_set, 'question_order_mode', 'difficulty_ascending') or 'difficulty_ascending'
        if order_mode not in ['difficulty_ascending', 'full_shuffle']:
            order_mode = 'difficulty_ascending'
        print(f"[QUIZ PLAYLIST] Ordre des questions: {order_mode}")

        # Construire la requête de base selon le set de règles
        base_query = _apply_rule_set_filters(_base_questions_for_rule_set(rule_set, current_user_id, viewer_has_private_access=viewer_has_private_access), rule_set)

        # Préparer par difficulté avec logique keywords
        per_diff_ids: dict[int, list[int]] = {}
        used_keywords_global = set()
        all_stats = []

        for d in allowed_diffs:
            quota = int(qmap.get(str(d), 0) or 0)
            if quota <= 0:
                per_diff_ids[d] = []
                continue

            print(f"[QUIZ PLAYLIST] Difficulté {d}: quota={quota}")

            q_for_diff = base_query.filter(Question.difficulty_level == d)
            candidates = q_for_diff.with_entities(Question.id).all()
            candidate_ids = [row.id for row in candidates]

            print(f"[QUIZ PLAYLIST]   Candidats disponibles: {len(candidate_ids)}")

            # Appliquer la logique keywords
            chosen, used_keywords_global, stats = _select_questions_with_keyword_logic(
                candidate_ids=candidate_ids,
                seen_question_ids=seen_ids,
                used_keywords=used_keywords_global,
                answered_keywords=answered_keywords,
                prevent_duplicate_keywords=prevent_duplicate_keywords,
                quota=quota
            )

            per_diff_ids[d] = chosen
            all_stats.append({
                'difficulty': d,
                'quota': quota,
                'selected': len(chosen),
                'perfect': stats['perfect'],
                'conditions': stats['conditions_met']
            })

            print(f"[QUIZ PLAYLIST]   Sélectionnés: {len(chosen)}/{quota}")
            if not stats['perfect']:
                for condition in stats['conditions_met']:
                    print(f"[QUIZ PLAYLIST]     {condition}")

        # Construire la playlist selon le mode d'ordre choisi
        if order_mode == 'full_shuffle':
            playlist = []
            for diff in per_diff_ids:
                playlist.extend(per_diff_ids[diff])
            random.shuffle(playlist)
        else:
            playlist = []
            for diff in sorted(per_diff_ids.keys()):
                bucket = list(per_diff_ids.get(diff) or [])
                if len(bucket) > 1:
                    random.shuffle(bucket)
                playlist.extend(bucket)

        expected_total = sum(int(qmap.get(str(d), 0) or 0) for d in allowed_diffs)

        # Logs finaux
        print("\n[QUIZ PLAYLIST] === RÉSUMÉ FINAL ===")
        print(f"[QUIZ PLAYLIST] Playlist générée: {len(playlist)}/{expected_total} questions")

        # Vérifier si toutes les conditions sont parfaites
        all_perfect = all(stat['perfect'] for stat in all_stats)
        if all_perfect:
            print("[QUIZ PLAYLIST] CONDITIONS PARFAITES pour toutes les questions !")
        else:
            print("[QUIZ PLAYLIST] COMPROMIS NECESSAIRES:")
            for stat in all_stats:
                if not stat['perfect']:
                    print(f"[QUIZ PLAYLIST]   Difficulté {stat['difficulty']}: {', '.join(stat['conditions'])}")

        if len(playlist) < expected_total:
            print("[QUIZ PLAYLIST] Playlist incomplete. Pool insuffisant pour certains quotas.")

        print(f"[QUIZ PLAYLIST] Keywords uniques utilisés: {len(used_keywords_global)}")
        print("[QUIZ PLAYLIST] ==================\n")

        return playlist
    except Exception as e:
        print(f"[QUIZ PLAYLIST] ERREUR generation playlist: {e}")
        import traceback
        traceback.print_exc()
        return []
