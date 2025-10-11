# Quiz Géocaching - Application de Gestion

Application Flask pour gérer une base de données de questions de quiz sur le géocaching avec une interface moderne utilisant HTMX et hyperscript.

## 🎯 Fonctionnalités

- ✅ **CRUD complet** : Création, lecture, édition et suppression de questions
- ✅ **Interface moderne** : Design responsive avec HTMX pour des interactions fluides
- ✅ **Recherche en temps réel** : Filtrez les questions instantanément
- ✅ **Gestion complète** : Tous les champs nécessaires pour des questions de quiz détaillées
- ✅ **Support multilingue** : Système de liens entre traductions
- ✅ **Statistiques** : Suivi du taux de réussite et du nombre de réponses
- ✅ **Thématiques** : Organisation par thèmes larges et précis

## 🚀 Démarrage rapide

### 1. Installer les dépendances

```bash
pip install -r requirements.txt
```

### 2. Initialiser la base de données (optionnel)

Pour créer la base de données avec des exemples de questions :

```bash
python init_db.py
```

### 3. Lancer l'application

```bash
python app.py
```

### 4. Accéder à l'application

Ouvrez votre navigateur à l'adresse :
```
http://localhost:5000
```

## 📊 Structure de la base de données

La table **Questions** contient les champs suivants :

| Champ | Type | Description |
|-------|------|-------------|
| `id` | Integer | Identifiant unique |
| `created_at` | DateTime | Date de création |
| `updated_at` | DateTime | Date de dernière modification |
| `author` | String | Auteur de la question |
| `question_text` | Text | Intitulé de la question |
| `possible_answers` | Text | Réponses possibles (séparées par '|||') |
| `answer_images` | Text | URLs des images pour les réponses |
| `correct_answer` | String | Numéro de la bonne réponse |
| `detailed_answer` | Text | Explication détaillée |
| `hint` | Text | Indice optionnel |
| `broad_theme` | String | Thématique large (ex: Règles, Histoire) |
| `specific_theme` | String | Thématique précise (ex: Reviewers, GPS) |
| `country` | String | Pays spécifique si applicable |
| `difficulty_level` | Integer | Niveau de difficulté (1-5) |
| `success_rate` | Float | Pourcentage de réussite |
| `times_answered` | Integer | Nombre de fois répondue |
| `translation_id` | Integer | ID de la question dans une autre langue |
| `is_published` | Boolean | Statut de publication |

## 🛠️ Technologies utilisées

- **Backend**: Flask 3.0, SQLAlchemy
- **Frontend**: HTML5, HTMX 1.9, hyperscript 0.9
- **Base de données**: SQLite (facilement changeable pour PostgreSQL, MySQL, etc.)
- **Styling**: CSS moderne avec variables CSS et animations

## 📁 Structure du projet

```
QuizGeocaching/
├── app.py                  # Application Flask principale
├── models.py               # Modèles SQLAlchemy
├── config.py               # Configuration
├── init_db.py              # Script d'initialisation de la DB
├── requirements.txt        # Dépendances Python
├── static/
│   └── style.css          # Feuille de style
└── templates/
    ├── base.html          # Template de base
    ├── index.html         # Page d'accueil
    ├── questions_list.html # Liste des questions
    └── question_form.html  # Formulaire d'édition
```

## 💡 Utilisation

### Créer une nouvelle question

1. Cliquez sur le bouton **"+ Nouvelle Question"**
2. Remplissez les champs du formulaire
3. Ajoutez autant de réponses possibles que nécessaire
4. Indiquez le numéro de la bonne réponse
5. Cliquez sur **"Créer"**

### Éditer une question

1. Cliquez sur l'icône ✏️ sur la carte de la question
2. Modifiez les champs souhaités
3. Cliquez sur **"Mettre à jour"**

### Supprimer une question

1. Cliquez sur l'icône 🗑️ sur la carte de la question
2. Confirmez la suppression

### Rechercher des questions

Utilisez la barre de recherche pour filtrer les questions par :
- Texte de la question
- Auteur
- Thématique large
- Thématique précise

## 🔧 Configuration

Pour personnaliser l'application, vous pouvez modifier le fichier `config.py` :

```python
# Exemple de configuration pour une base de données PostgreSQL
SQLALCHEMY_DATABASE_URI = 'postgresql://user:password@localhost/geocaching_quiz'
```

## 🌍 Support des traductions

Le système de traductions permet de lier des questions dans différentes langues :

1. Créez la question dans la langue principale
2. Notez son ID (visible dans l'URL ou la carte)
3. Créez la traduction dans une autre langue
4. Dans le champ "ID de traduction", indiquez l'ID de la question originale

Cela permet de :
- Comparer les taux de réussite selon les pays
- Faciliter la gestion multilingue
- Maintenir la cohérence entre les versions

## 📈 Prochaines étapes possibles

- [ ] Ajout d'un système d'authentification
- [ ] Export/Import de questions (JSON, CSV)
- [ ] Interface de quiz pour tester les questions
- [ ] Statistiques avancées et graphiques
- [ ] API REST pour intégration externe
- [ ] Upload d'images pour les questions et réponses

## 📝 Licence

Ce projet est libre d'utilisation pour vos besoins de géocaching !

