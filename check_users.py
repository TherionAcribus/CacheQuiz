from app import app
from models import db, User

with app.app_context():
    users = User.query.all()
    print("Utilisateurs existants:")
    for u in users[:5]:
        print(f"- {u.username} (email: {u.email}, has_password: {bool(u.password_hash)})")
