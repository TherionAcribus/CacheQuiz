# Identifiants Administrateur

## Administrateur par défaut

Lors du premier lancement de l'application, un administrateur par défaut est automatiquement créé avec les identifiants suivants :

- **Username** : `admin`
- **Password** : `admin123`
- **Email** : `admin@geocaching-quiz.com`

## ⚠️ Sécurité importante

**CHANGEZ IMMÉDIATEMENT ce mot de passe après la première connexion !**

### Comment changer le mot de passe :

1. Connectez-vous avec `admin` / `admin123`
2. Allez dans votre profil utilisateur
3. Modifiez votre mot de passe
4. Déconnectez-vous et reconnectez-vous avec le nouveau mot de passe

## Création d'autres administrateurs

Une fois connecté en tant qu'admin, vous pouvez :

1. Aller dans la section "Administration" > "Utilisateurs"
2. Créer de nouveaux utilisateurs
3. Leur assigner le profil "Administrateur"

## Profils disponibles

- **Administrateur** : Accès complet à toutes les fonctionnalités
- **Éditeur** : Peut créer et gérer ses propres questions/règles
- **Modérateur** : Peut modérer toutes les questions et règles
- **Lecteur** : Accès en lecture seule à l'administration

## En production

Sur PythonAnywhere ou tout autre environnement de production :

1. Lancez `python init_prod_db.py` pour initialiser la base
2. L'admin par défaut sera créé automatiquement
3. Changez immédiatement le mot de passe par sécurité
