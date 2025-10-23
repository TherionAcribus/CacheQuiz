# Modes de sélection des questions dans QuizRuleSet

## Vue d'ensemble

Le système de règles de quiz supporte maintenant **deux modes de sélection des questions** :

### 1. Mode Automatique (`auto`) - Par défaut
Les questions sont sélectionnées automatiquement selon des critères :
- **Thèmes larges** : Tous ou sélection spécifique
- **Sous-thèmes** : Tous ou sélection spécifique
- **Difficultés** : Liste des niveaux autorisés (1-5)
- **Quotas par difficulté** : Nombre de questions par niveau

**Utilisation typique** : Quiz génériques, entraînement par thème, quiz aléatoires

### 2. Mode Manuel (`manual`) - Nouveau
Les questions sont sélectionnées individuellement par l'utilisateur.
- L'utilisateur choisit une **liste spécifique de questions**
- Le système tire au sort parmi ce pool de questions
- Les critères de thèmes/difficultés sont ignorés en mode manuel

**Utilisation typique** : Quiz personnalisés, révisions ciblées, défis spécifiques

---

## Structure de la base de données

### Nouvelle colonne dans `quiz_rule_sets`
```python
question_selection_mode = db.Column(db.String(20), nullable=False, default='auto')
# Valeurs possibles : 'auto' | 'manual'
```

### Nouvelle table d'association `quiz_rule_set_questions`
```python
quiz_rule_set_questions = db.Table(
    'quiz_rule_set_questions',
    db.Column('rule_set_id', db.Integer, db.ForeignKey('quiz_rule_sets.id'), primary_key=True),
    db.Column('question_id', db.Integer, db.ForeignKey('questions.id'), primary_key=True)
)
```

### Nouvelle relation dans `QuizRuleSet`
```python
selected_questions = db.relationship(
    'Question',
    secondary=quiz_rule_set_questions,
    lazy='subquery',
    backref=db.backref('used_in_rule_sets', lazy='dynamic')
)
```

---

## Utilisation dans le code

### Vérifier le mode de sélection
```python
rule = QuizRuleSet.query.get(rule_id)

if rule.question_selection_mode == 'auto':
    # Logique de sélection automatique par thèmes/difficultés
    questions = get_questions_by_criteria(rule)
elif rule.question_selection_mode == 'manual':
    # Utiliser la liste de questions prédéfinies
    questions = rule.selected_questions
```

### Créer une règle en mode manuel
```python
# Créer la règle
rule = QuizRuleSet(
    name="Quiz personnalisé",
    question_selection_mode='manual',
    created_by_user_id=current_user.id
)

# Ajouter des questions spécifiques
question1 = Question.query.get(42)
question2 = Question.query.get(73)
question3 = Question.query.get(156)

rule.selected_questions.extend([question1, question2, question3])

db.session.add(rule)
db.session.commit()
```

### Modifier les questions d'une règle manuelle
```python
rule = QuizRuleSet.query.get(rule_id)

if rule.question_selection_mode == 'manual':
    # Remplacer toutes les questions
    rule.selected_questions = Question.query.filter(Question.id.in_([1, 2, 3, 4, 5])).all()
    
    # Ou ajouter des questions
    new_question = Question.query.get(99)
    rule.selected_questions.append(new_question)
    
    # Ou retirer une question
    rule.selected_questions.remove(question_to_remove)
    
    db.session.commit()
```

---

## Migration

Pour mettre à jour une base de données existante :

```bash
python migrate_add_manual_question_selection.py
```

Ce script :
1. Crée la table `quiz_rule_set_questions`
2. Ajoute la colonne `question_selection_mode` à `quiz_rule_sets`
3. Met à jour toutes les règles existantes avec le mode `'auto'` par défaut

---

## Interface utilisateur (à implémenter)

### Dans le formulaire de création/édition de règle

**Onglet "Général"** :
```
[ ] Mode de sélection des questions
    ( ) Automatique - Par thèmes et difficultés
    ( ) Manuel - Sélection individuelle de questions
```

**Si mode "Automatique"** :
- Afficher les onglets "Thèmes" et "Timer & Difficultés" (existants)

**Si mode "Manuel"** :
- Afficher un nouvel onglet "Sélection de questions"
- Interface de recherche/filtrage de questions
- Liste des questions sélectionnées avec possibilité de retirer
- Compteur : "X questions sélectionnées"

---

## Avantages

### Mode Automatique
✅ Génération dynamique de quiz variés
✅ Facile à configurer
✅ S'adapte automatiquement aux nouvelles questions ajoutées

### Mode Manuel
✅ Contrôle total sur les questions posées
✅ Création de quiz thématiques très spécifiques
✅ Révisions ciblées sur des questions précises
✅ Défis personnalisés entre utilisateurs

---

## Exemples d'utilisation

### Exemple 1 : Quiz de révision personnalisé
Un utilisateur veut réviser uniquement les questions qu'il a ratées :
```python
failed_questions = get_user_failed_questions(user_id)
rule = QuizRuleSet(
    name="Mes questions ratées",
    question_selection_mode='manual',
    selected_questions=failed_questions
)
```

### Exemple 2 : Défi entre amis
Un utilisateur crée un quiz avec 10 questions très difficiles :
```python
hard_questions = Question.query.filter_by(difficulty_level=5).limit(10).all()
rule = QuizRuleSet(
    name="Défi expert",
    question_selection_mode='manual',
    selected_questions=hard_questions
)
```

### Exemple 3 : Quiz thématique précis
Un quiz sur des questions très spécifiques (ex: "Capitales européennes commençant par B") :
```python
specific_questions = [q1, q2, q3, q4, q5]  # Sélectionnées manuellement
rule = QuizRuleSet(
    name="Capitales en B",
    question_selection_mode='manual',
    selected_questions=specific_questions
)
```

---

## Notes techniques

1. **Compatibilité** : Les règles existantes continuent de fonctionner en mode `'auto'` par défaut
2. **Validation** : En mode `'manual'`, il faut au moins 1 question sélectionnée
3. **Performance** : La relation `selected_questions` utilise `lazy='subquery'` pour optimiser les requêtes
4. **Tirage au sort** : Même en mode manuel, le système peut tirer au sort parmi les questions sélectionnées (selon les paramètres de la règle)

