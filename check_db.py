import sqlite3

conn = sqlite3.connect('instance/geocaching_quiz.db')
cursor = conn.cursor()

# Vérifier les profils
cursor.execute('SELECT id, name FROM profiles')
profiles = cursor.fetchall()
print('Profils:', profiles)

# Trouver le profil Administrateur
admin_profile_id = None
for p in profiles:
    if p[1] == 'Administrateur':
        admin_profile_id = p[0]
        break

if admin_profile_id:
    print(f'ID du profil Administrateur: {admin_profile_id}')

    # Voir les utilisateurs avec ce profil
    cursor.execute('SELECT id, username, email, is_active FROM users WHERE profile_id = ?', (admin_profile_id,))
    admins = cursor.fetchall()
    print('Administrateurs:', admins)
else:
    print('Profil Administrateur non trouvé!')

# Vérifier contact_messages
cursor.execute('SELECT COUNT(*) FROM contact_messages')
count = cursor.fetchone()[0]
print(f'Nombre de messages de contact: {count}')

if count > 0:
    cursor.execute('SELECT id, visitor_name, visitor_email, created_at FROM contact_messages ORDER BY created_at DESC LIMIT 5')
    rows = cursor.fetchall()
    print('Derniers messages:', rows)

conn.close()
