from flask import render_template, request, make_response, g
from models import db, Question, User, BroadTheme, SpecificTheme
from auth import _ensure_admin_page_redirect, _ensure_perm_api
from datetime import datetime
import json
import csv
from io import StringIO


def export_page():
    resp = _ensure_admin_page_redirect()
    if resp:
        return resp
    themes = BroadTheme.query.order_by(BroadTheme.name.asc()).all()
    specific_themes = SpecificTheme.query.order_by(SpecificTheme.name.asc()).all()
    return render_template('export.html', themes=themes, specific_themes=specific_themes)


def _export_base_query():
    query = Question.query.join(User, Question.author_id == User.id).join(BroadTheme, Question.broad_theme_id == BroadTheme.id, isouter=True).join(SpecificTheme, Question.specific_theme_id == SpecificTheme.id, isouter=True)
    return query


def _apply_export_filters(query):
    # Filtres
    q = (request.args.get('q') or '').strip()
    if q:
        query = query.filter(
            db.or_(
                Question.question_text.contains(q),
                Question.detailed_answer.contains(q),
                Question.hint.contains(q),
                User.username.contains(q),
                BroadTheme.name.contains(q),
                SpecificTheme.name.contains(q)
            )
        )

    # Filtre par auteur
    author_filter = request.args.get('author_filter', 'mine')  # Par défaut: mes questions uniquement
    if author_filter == 'mine':
        user = getattr(g, 'current_user', None)
        if user:
            query = query.filter(Question.author_id == user.id)
        else:
            # Si pas d'utilisateur connecté, ne montrer aucune question
            query = query.filter(False)

    publication_status = request.args.get('publication_status')
    if publication_status == 'published':
        query = query.filter(Question.is_published.is_(True))
    elif publication_status == 'unpublished':
        query = query.filter(Question.is_published.is_(False))

    try:
        diff_min = int(request.args.get('diff_min')) if request.args.get('diff_min') else None
        diff_max = int(request.args.get('diff_max')) if request.args.get('diff_max') else None
    except ValueError:
        diff_min = diff_max = None
    if diff_min is not None:
        query = query.filter(Question.difficulty_level >= diff_min)
    if diff_max is not None:
        query = query.filter(Question.difficulty_level <= diff_max)

    theme_id = request.args.get('broad_theme_id')
    if theme_id and theme_id.isdigit():
        query = query.filter(Question.broad_theme_id == int(theme_id))

    specific_theme_id = request.args.get('specific_theme_id')
    if specific_theme_id and specific_theme_id.isdigit():
        query = query.filter(Question.specific_theme_id == int(specific_theme_id))

    # Filtres par date
    created_after = request.args.get('created_after')
    if created_after:
        try:
            created_after_date = datetime.strptime(created_after, '%Y-%m-%d')
            query = query.filter(Question.created_at >= created_after_date)
        except ValueError:
            pass  # Ignorer si format invalide

    created_before = request.args.get('created_before')
    if created_before:
        try:
            created_before_date = datetime.strptime(created_before, '%Y-%m-%d')
            # Inclure toute la journée (jusqu'à 23:59:59)
            created_before_date = created_before_date.replace(hour=23, minute=59, second=59, microsecond=999999)
            query = query.filter(Question.created_at <= created_before_date)
        except ValueError:
            pass  # Ignorer si format invalide

    return query


def _serialize_question_for_export(q: Question):
    answers = (q.possible_answers or '').split('|||') if q.possible_answers else []
    return {
        'id': q.id,
        'auteur': q.author_user.username if q.author_user else None,
        'theme': q.theme.name if q.theme else None,
        'soustheme': q.specific_theme_obj.name if q.specific_theme_obj else None,
        'difficulte': q.difficulty_level,
        'question': q.question_text,
        'propositions': answers,
        'indice': q.hint,
        'reponse_detaillee': q.detailed_answer,
        'bonne_reponse_index': q.correct_answer,
        'publie': q.is_published,
        'cree_le': q.created_at.isoformat() if q.created_at else None,
        'modifie_le': q.updated_at.isoformat() if q.updated_at else None,
        'source': q.source,
    }


def export_download():
    denied = _ensure_perm_api()
    if denied:
        return denied

    fmt = (request.args.get('format') or 'csv').lower()  # csv, json, jsonl, md
    page = int(request.args.get('page', 1) or 1)
    page_size = int(request.args.get('page_size', 200) or 200)
    page = max(page, 1)
    page_size = max(1, min(page_size, 2000))

    query = _apply_export_filters(_export_base_query()).order_by(Question.id.asc())

    total = query.count()
    items = query.offset((page - 1) * page_size).limit(page_size).all()
    rows = [_serialize_question_for_export(q) for q in items]

    filename = f"export_questions_p{page}_n{len(rows)}.{fmt}"

    if fmt == 'json':
        data = json.dumps({'total': total, 'page': page, 'page_size': page_size, 'count': len(rows), 'items': rows}, ensure_ascii=False, indent=2)
        resp = make_response(data)
        resp.headers['Content-Type'] = 'application/json; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

    if fmt == 'jsonl':
        lines = '\n'.join([json.dumps(r, ensure_ascii=False) for r in rows])
        resp = make_response(lines)
        resp.headers['Content-Type'] = 'application/x-ndjson; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

    if fmt == 'md' or fmt == 'markdown':
        def md_escape(text):
            if text is None:
                return ''
            return str(text).replace('\r', '').strip()
        md_lines = []
        for r in rows:
            md_lines.append(f"### Q{r['id']} · D{r['difficulte']} · {r['theme'] or '-'} / {r['soustheme'] or '-'}")
            md_lines.append('')
            md_lines.append(md_escape(r['question']))
            md_lines.append('')
            for i, ans in enumerate(r['propositions'], start=1):
                marker = '✅' if str(i) == str(r['bonne_reponse_index'] or '') else '▫️'
                md_lines.append(f"- {marker} {md_escape(ans)}")
            if r['indice']:
                md_lines.append('')
                md_lines.append(f"Hint: {md_escape(r['indice'])}")
            if r['reponse_detaillee']:
                md_lines.append('')
                md_lines.append(f"Réponse: {md_escape(r['reponse_detaillee'])}")
            md_lines.append('')
            md_lines.append('---')
            md_lines.append('')
        data = '\n'.join(md_lines)
        resp = make_response(data)
        resp.headers['Content-Type'] = 'text/markdown; charset=utf-8'
        resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
        return resp

    # Par défaut: CSV
    import csv
    from io import StringIO
    csv_buf = StringIO()
    writer = csv.writer(csv_buf)
    writer.writerow(['id', 'auteur', 'theme', 'soustheme', 'difficulte', 'question', 'proposition_1', 'proposition_2', 'proposition_3', 'proposition_4', 'proposition_5', 'proposition_6', 'indice', 'reponse_detaillee', 'bonne_reponse_index', 'publie'])
    for r in rows:
        props = list(r['propositions']) if r['propositions'] else []
        props = props + [''] * (6 - len(props))  # normaliser sur 6 colonnes max
        writer.writerow([
            r['id'], r['auteur'] or '', r['theme'] or '', r['soustheme'] or '', r['difficulte'] or '',
            (r['question'] or '').replace('\r', '').replace('\n', ' ').strip(),
            (props[0] or '').replace('\r', '').replace('\n', ' ').strip(),
            (props[1] or '').replace('\r', '').replace('\n', ' ').strip(),
            (props[2] or '').replace('\r', '').replace('\n', ' ').strip(),
            (props[3] or '').replace('\r', '').replace('\n', ' ').strip(),
            (props[4] or '').replace('\r', '').replace('\n', ' ').strip(),
            (props[5] or '').replace('\r', '').replace('\n', ' ').strip(),
            (r['indice'] or '').replace('\r', '').replace('\n', ' ').strip(),
            (r['reponse_detaillee'] or '').replace('\r', '').replace('\n', ' ').strip(),
            r['bonne_reponse_index'] or '',
            '1' if r['publie'] else '0'
        ])
    resp = make_response(csv_buf.getvalue())
    resp.headers['Content-Type'] = 'text/csv; charset=utf-8'
    resp.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
    return resp
