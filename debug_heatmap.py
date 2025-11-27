from app import app
from models import db, Question, BroadTheme, SpecificTheme
from sqlalchemy import func

with app.app_context():
    # Vérifions quelques questions
    questions = Question.query.limit(5).all()
    print("=== Quelques questions ===")
    for q in questions:
        print(f'Question {q.id}: difficulty={q.difficulty_level}, broad_theme_id={q.broad_theme_id}, specific_theme_id={q.specific_theme_id}, published={q.is_published}')

    # Comptons les questions par difficulté et thème
    print("\n=== Comptage des questions ===")
    results = db.session.query(
        Question.difficulty_level,
        Question.broad_theme_id,
        Question.specific_theme_id,
        func.count(Question.id)
    ).group_by(
        Question.difficulty_level,
        Question.broad_theme_id,
        Question.specific_theme_id
    ).all()

    for r in results:
        print(f'difficulty={r[0]}, broad_theme={r[1]}, specific_theme={r[2]}, count={r[3]}')

    # Test de la requête de heatmap
    print("\n=== Test de la requête heatmap (broad themes) ===")
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

    rows = base.group_by('difficulty', 'theme_id', 'theme_name').all()

    print(f"Nombre de résultats: {len(rows)}")
    for r in rows:
        print(f'difficulty={r.difficulty}, theme_id={r.theme_id}, theme_name={r.theme_name}, count={r.count}')
