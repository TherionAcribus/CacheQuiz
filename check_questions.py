#!/usr/bin/env python3
from models import db, Question, BroadTheme, SpecificTheme
from app import app

app.app_context().push()

print('Questions par thème large:')
themes = BroadTheme.query.all()
for t in themes:
    count = Question.query.filter_by(broad_theme_id=t.id).count()
    print(f'  {t.name}: {count}')

print('Questions par difficulté:')
for d in range(1,6):
    count = Question.query.filter_by(difficulty_level=d).count()
    print(f'  Difficulté {d}: {count}')

print('Questions par sous-thème:')
subthemes = SpecificTheme.query.all()
for st in subthemes:
    count = Question.query.filter_by(specific_theme_id=st.id).count()
    print(f'  {st.name}: {count}')

print('Total questions:', Question.query.count())
