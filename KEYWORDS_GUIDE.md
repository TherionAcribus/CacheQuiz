# Guide des Mots-clés (Keywords)

## Vue d'ensemble

Les **mots-clés** (ou sujets précis) sont une nouvelle fonctionnalité qui permet d'éviter de poser deux questions sur le même sujet précis au cours d'un quiz.

### Différence avec les thèmes

- **Thèmes larges** : catégories générales (ex: "Histoire du géocaching")
- **Sous-thèmes** : sous-catégories (ex: "Origines")
- **Mots-clés** : sujets très précis (ex: "première cache", "mingo", "Dave Ulmer")

## Structure des données

### Modèle Keyword

```python
class Keyword(db.Model):
    id              # Identifiant unique
    name            # Nom du mot-clé (ex: "première cache")
    description     # Description optionnelle
    language        # Code langue (fr, en, etc.)
    translation_id  # Lien vers la traduction
    questions       # Questions associées (many-to-many)
```

### Relations

- **Question ↔ Keyword** : Une question peut avoir plusieurs mots-clés, un mot-clé peut être associé à plusieurs questions
- **QuizRuleSet ↔ Keyword** : Un ensemble de règles peut filtrer par mots-clés ou empêcher les doublons

## Utilisation dans les Questions

### Ajouter des mots-clés à une question

```python
# Créer ou récupérer un mot-clé
keyword = Keyword(name="première cache", language="fr")
db.session.add(keyword)

# Associer à une question
question.keywords.append(keyword)
db.session.commit()
```

### Récupérer les mots-clés d'une question

```python
# Via la relation
keywords = question.keywords

# Via le dictionnaire
question_dict = question.to_dict()
keywords = question_dict['keywords']  # Liste de dicts
```

## Utilisation dans les Quiz

### Configuration du QuizRuleSet

Trois paramètres permettent de gérer les mots-clés dans un quiz :

#### 1. `prevent_duplicate_keywords` (booléen, défaut: True)

Empêche qu'un même mot-clé apparaisse deux fois dans le quiz.

**Exemple** : Si deux questions ont le mot-clé "première cache", une seule sera sélectionnée.

```python
rule_set.prevent_duplicate_keywords = True  # Pas de doublons
rule_set.prevent_duplicate_keywords = False # Doublons autorisés
```

#### 2. `use_all_keywords` (booléen, défaut: True)

Détermine si on utilise tous les mots-clés ou seulement une sélection.

```python
rule_set.use_all_keywords = True   # Tous les mots-clés
rule_set.use_all_keywords = False  # Seulement ceux dans allowed_keywords
```

#### 3. `allowed_keywords` (relation many-to-many)

Liste des mots-clés autorisés (utilisé uniquement si `use_all_keywords = False`).

```python
# Filtrer uniquement certains mots-clés
rule_set.use_all_keywords = False
rule_set.allowed_keywords = [keyword1, keyword2, keyword3]
```

### Scénarios d'utilisation

#### Scénario 1 : Quiz sans contrainte de mots-clés

```python
rule_set.prevent_duplicate_keywords = False
rule_set.use_all_keywords = True
# → Aucune restriction sur les mots-clés
```

#### Scénario 2 : Quiz sans doublons de sujets (recommandé)

```python
rule_set.prevent_duplicate_keywords = True
rule_set.use_all_keywords = True
# → Pas de doublon de mots-clés, tous autorisés
```

#### Scénario 3 : Quiz sur des sujets spécifiques uniquement

```python
rule_set.prevent_duplicate_keywords = True
rule_set.use_all_keywords = False
rule_set.allowed_keywords = [keyword_premiere_cache, keyword_mingo]
# → Uniquement les questions avec ces mots-clés, sans doublons
```

## Exemples pratiques

### Exemple 1 : Questions sur le géocaching

```python
# Créer des mots-clés
kw_premiere = Keyword(name="première cache", language="fr")
kw_mingo = Keyword(name="mingo", language="fr")
kw_dave = Keyword(name="Dave Ulmer", language="fr")

# Question 1 : Qui a créé la première cache ?
question1.keywords = [kw_premiere, kw_dave]

# Question 2 : Où était la première cache ?
question2.keywords = [kw_premiere]

# Question 3 : Qu'est-ce qu'un mingo ?
question3.keywords = [kw_mingo]

# Quiz avec prevent_duplicate_keywords = True
# → Question1 OU Question2 sera sélectionnée (pas les deux)
# → Question3 peut être sélectionnée
```

### Exemple 2 : Gestion des traductions

```python
# Version française
kw_fr = Keyword(name="première cache", language="fr")

# Version anglaise (liée)
kw_en = Keyword(name="first cache", language="en", translation_id=kw_fr.id)

# Même logique de doublon par langue
```

## Migration

Pour appliquer les changements à la base de données :

```bash
python migrate_add_keywords.py
```

Cette migration crée :
- Table `keywords`
- Table d'association `question_keywords`
- Table d'association `quiz_rule_set_keywords`
- Colonnes `prevent_duplicate_keywords` et `use_all_keywords` dans `quiz_rule_sets`

## API et Sérialisation

### Question.to_dict()

```python
{
    ...
    'keywords': [
        {'id': 1, 'name': 'première cache', 'language': 'fr'},
        {'id': 2, 'name': 'mingo', 'language': 'fr'}
    ],
    ...
}
```

### Keyword.to_dict()

```python
{
    'id': 1,
    'name': 'première cache',
    'description': 'Première cache géocaching au monde',
    'language': 'fr',
    'translation_id': None,
    'question_count': 5
}
```

## Bonnes pratiques

1. **Soyez spécifique** : Un mot-clé doit représenter un sujet très précis
2. **Évitez les doublons de concepts** : "première cache" vs "first cache" → utiliser la traduction
3. **Optionnel** : N'ajoutez des mots-clés que quand c'est nécessaire
4. **Par défaut vide** : Les questions sans mot-clé sont toujours sélectionnables
5. **Activez prevent_duplicate_keywords** : Pour une meilleure expérience utilisateur

## Questions fréquentes

### Q : Que se passe-t-il si une question n'a pas de mot-clé ?

**R :** Elle peut être sélectionnée normalement. Les mots-clés sont optionnels.

### Q : Peut-on avoir plusieurs questions avec le même mot-clé ?

**R :** Oui, mais dans un même quiz, si `prevent_duplicate_keywords = True`, une seule sera sélectionnée.

### Q : Comment éviter les doublons entre thèmes et mots-clés ?

**R :** Les thèmes et mots-clés servent des objectifs différents :
- **Thèmes** : classification et filtrage large
- **Mots-clés** : éviter les doublons de sujets précis dans un quiz

### Q : Faut-il mettre un mot-clé sur chaque question ?

**R :** Non, seulement sur les questions traitant d'un sujet très spécifique que vous ne voulez pas voir apparaître deux fois.

## Implémentation dans l'interface

À implémenter dans vos formulaires :

1. **Formulaire de question** :
   - Champ de sélection multiple pour les mots-clés
   - Bouton "Créer un nouveau mot-clé"

2. **Formulaire de règle de quiz** :
   - Case à cocher "Empêcher les doublons de mots-clés"
   - Sélection des mots-clés autorisés (si use_all_keywords = False)

3. **Gestion des mots-clés** :
   - Page de liste des mots-clés
   - Édition/suppression
   - Gestion des traductions

