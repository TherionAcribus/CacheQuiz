import sqlite3

conn = sqlite3.connect('instance/geocaching_quiz.db')
cursor = conn.cursor()

print("Vérification de la structure actuelle de conversation_messages...")

# Vérifier la structure actuelle
cursor.execute("PRAGMA table_info(conversation_messages)")
columns = cursor.fetchall()
print("Colonnes actuelles:", [col[1] for col in columns])

# Vérifier si sender_id permet NULL
sender_id_col = None
for col in columns:
    if col[1] == 'sender_id':
        sender_id_col = col
        break

if sender_id_col:
    print(f"sender_id info: {sender_id_col}")
    if sender_id_col[3] == 0:  # notnull = 0 signifie nullable
        print("sender_id est déjà nullable ✓")
    else:
        print("sender_id n'est pas nullable, il faut le corriger...")

        # Recréer la table avec sender_id nullable
        print("Création de la nouvelle table...")
        cursor.execute("""
            CREATE TABLE conversation_messages_new (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                created_at DATETIME NOT NULL,
                updated_at DATETIME NOT NULL,
                conversation_id INTEGER NOT NULL,
                sender_id INTEGER,
                content TEXT NOT NULL,
                FOREIGN KEY(conversation_id) REFERENCES conversations(id),
                FOREIGN KEY(sender_id) REFERENCES users(id)
            )
        """)

        print("Copie des données...")
        cursor.execute("""
            INSERT INTO conversation_messages_new (id, created_at, updated_at, conversation_id, sender_id, content)
            SELECT id, created_at, updated_at, conversation_id, sender_id, content FROM conversation_messages
        """)

        print("Suppression de l'ancienne table...")
        cursor.execute("DROP TABLE conversation_messages")

        print("Renommage de la nouvelle table...")
        cursor.execute("ALTER TABLE conversation_messages_new RENAME TO conversation_messages")

        print("Migration terminée !")
else:
    print("sender_id est déjà nullable ✓")

conn.commit()
conn.close()

print("Vérification finale...")
conn = sqlite3.connect('instance/geocaching_quiz.db')
cursor = conn.cursor()
cursor.execute("PRAGMA table_info(conversation_messages)")
columns = cursor.fetchall()
sender_id_col = None
for col in columns:
    if col[1] == 'sender_id':
        sender_id_col = col
        break
if sender_id_col:
    print(f"sender_id après migration: notnull={sender_id_col[3]} (0=nullable, 1=not null)")
conn.close()
