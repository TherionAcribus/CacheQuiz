from app import app
from models import db, Question, BroadTheme, SpecificTheme
from sqlalchemy import func
from flask import request

with app.app_context():
    with app.test_request_context('/api/heatmap?mode=broad'):
        # Reproduire exactement le code de heatmap_data
        mode = request.args.get('mode', 'broad')  # 'broad' ou 'specific'
        only_published = request.args.get('only_published') in ('1', 'true', 'yes', 'on')

        print(f"mode: {mode}")
        print(f"only_published: {only_published}")

        # Déterminer la liste des difficultés présentes
        diff_query = db.session.query(Question.difficulty_level).distinct()
        if only_published:
            diff_query = diff_query.filter(Question.is_published.is_(True))
        difficulties = sorted({row[0] for row in diff_query.all() if row[0] is not None}) or [1, 2, 3, 4, 5]
        print(f"difficulties: {difficulties}")

        # Colonnes et agrégations
        if mode == 'specific':
            join_model = SpecificTheme
            join_on = Question.specific_theme_id == SpecificTheme.id
            name_col = SpecificTheme.name
            id_col = SpecificTheme.id
        else:
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
        print(f"Nombre de rows: {len(rows)}")

        # Récupérer l'ordre des thèmes
        themes = db.session.query(id_col, name_col).order_by(name_col.asc()).all()
        print(f"themes: {themes}")

        # Construire le mapping
        counts = {}
        max_count = 0
        for r in rows:
            d = int(r.difficulty) if r.difficulty is not None else None
            t_id = r.theme_id
            c = int(r.count)
            print(f"Processing row: d={d}, t_id={t_id}, c={c}")
            if d is None or t_id is None:
                print("  -> Ignored because d or t_id is None")
                continue
            counts.setdefault(d, {})[t_id] = c
            if c > max_count:
                max_count = c

        print(f"counts: {counts}")
        print(f"max_count: {max_count}")

        # Liste ordonnée
        theme_columns = [{'id': tid, 'name': tname} for tid, tname in themes]
        diff_rows = difficulties

        print(f"theme_columns: {theme_columns}")
        print(f"diff_rows: {diff_rows}")

        print(f"theme_columns and diff_rows: {bool(theme_columns and diff_rows)}")
