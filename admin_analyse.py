from flask import render_template, request
from models import db, Question, BroadTheme, SpecificTheme, QuestionAnswerStat, SavedQuestion
from auth import _ensure_admin_page_redirect, _ensure_perm_api
from sqlalchemy import func


def analysis_page():
    """Page d'analyse avec heatmap difficultés x thèmes."""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    # Valeurs par défaut de l'affichage
    default_mode = request.args.get('mode', 'broad')  # 'broad' ou 'specific'
    return render_template('analysis.html', default_mode=default_mode)


def heatmap_data():
    """Retourne un tableau heatmap HTML (HTMX) des comptes par difficulté x (thème/sous-thème)."""
    denied = _ensure_perm_api()
    if denied:
        return denied

    mode = request.args.get('mode', 'broad')  # 'broad' (thèmes) ou 'specific' (sous-thèmes)
    only_published = request.args.get('only_published') in ('1', 'true', 'yes', 'on')

    # Déterminer la liste des difficultés présentes (1..5 par défaut si vide)
    diff_query = db.session.query(Question.difficulty_level).distinct()
    if only_published:
        diff_query = diff_query.filter(Question.is_published.is_(True))
    difficulties = sorted({row[0] for row in diff_query.all() if row[0] is not None}) or [1, 2, 3, 4, 5]

    # Colonnes et agrégations
    if mode == 'specific':
        # Sous-thèmes
        join_model = SpecificTheme
        join_on = Question.specific_theme_id == SpecificTheme.id
        name_col = SpecificTheme.name
        id_col = SpecificTheme.id
        base = db.session.query(
            Question.difficulty_level.label('difficulty'),
            id_col.label('theme_id'),
            name_col.label('theme_name'),
            func.count(Question.id).label('count')
        ).outerjoin(join_model, join_on)
        if only_published:
            base = base.filter(Question.is_published.is_(True))
        rows = base.group_by('difficulty', 'theme_id', 'theme_name').all()

        # Récupérer l'ordre des sous-thèmes par nom
        themes = db.session.query(id_col, name_col).order_by(name_col.asc()).all()
    else:
        # Thèmes larges
        join_model = BroadTheme
        join_on = Question.broad_theme_id == BroadTheme.id
        name_col = BroadTheme.name
        id_col = BroadTheme.id
        base = db.session.query(
            Question.difficulty_level.label('difficulty'),
            id_col.label('theme_id'),
            name_col.label('theme_name'),
            func.count(Question.id).label('count')
        ).outerjoin(join_model, join_on)
        if only_published:
            base = base.filter(Question.is_published.is_(True))
        rows = base.group_by('difficulty', 'theme_id', 'theme_name').all()

        # Récupérer l'ordre des thèmes par nom
        themes = db.session.query(id_col, name_col).order_by(name_col.asc()).all()

    # Construire le mapping (difficulty -> theme_id -> count)
    counts = {}
    max_count = 0
    for r in rows:
        d = int(r.difficulty) if r.difficulty is not None else None
        t_id = r.theme_id
        c = int(r.count)
        if d is None or t_id is None:
            # Ignorer les entrées sans difficulté ou sans thème pour la heatmap
            continue
        counts.setdefault(d, {})[t_id] = c
        if c > max_count:
            max_count = c

    # Liste ordonnée des colonnes (thèmes) et des lignes (difficultés)
    theme_columns = [{'id': tid, 'name': tname} for tid, tname in themes]
    diff_rows = difficulties

    return render_template(
        'heatmap_table.html',
        mode=mode,
        only_published=only_published,
        theme_columns=theme_columns,
        diff_rows=diff_rows,
        counts=counts,
        max_count=max_count
    )


def question_stats_page(question_id: int):
    """Page admin des statistiques d'une question."""
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    q = Question.query.get_or_404(question_id)

    # Statistiques globales
    total_answers = q.times_answered or 0
    total_success = q.success_count or 0
    success_rate = (total_success / total_answers * 100.0) if total_answers > 0 else 0.0

    # Répartition des réponses
    distribution = []
    if q.possible_answers:
        answers = q.possible_answers.split('|||')
        # Précharger stats
        stats_rows = QuestionAnswerStat.query.filter_by(question_id=q.id).all()
        idx_to_count = {row.answer_index: (row.selected_count or 0) for row in stats_rows}
        for i, text in enumerate(answers, start=1):
            count = int(idx_to_count.get(i, 0))
            pct = (count / total_answers * 100.0) if total_answers > 0 else 0.0
            distribution.append({
                'index': i,
                'text': text,
                'count': count,
                'percent': pct,
                'is_correct': (str(i) == str(q.correct_answer or ''))
            })

    # Nombre de fois que la question est sauvegardée
    saved_count = SavedQuestion.query.filter_by(question_id=q.id).count()

    return render_template('question_stats.html', question=q,
                           total_answers=total_answers,
                           total_success=total_success,
                           success_rate=success_rate,
                           distribution=distribution,
                           saved_count=saved_count)
