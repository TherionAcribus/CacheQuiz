# Implémentation des routes API pour les Mots-clés

## Vue d'ensemble

Le formulaire de question (`question_form.html`) a été mis à jour pour gérer les mots-clés avec autocomplétion. Il vous reste maintenant à implémenter les routes API côté backend dans votre application Flask.

## Routes API nécessaires

### 1. GET `/api/keywords/json` - Liste tous les mots-clés

**Objectif** : Retourner la liste complète des mots-clés pour l'autocomplétion.

**Exemple d'implémentation** :

```python
@app.route('/api/keywords/json', methods=['GET'])
def api_keywords_json():
    """Retourne la liste de tous les mots-clés en JSON"""
    try:
        keywords = Keyword.query.order_by(Keyword.name).all()
        return jsonify([kw.to_dict() for kw in keywords])
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

**Réponse attendue** :
```json
[
  {
    "id": 1,
    "name": "première cache",
    "description": "Première cache géocaching au monde",
    "language": "fr",
    "translation_id": null,
    "question_count": 3
  },
  {
    "id": 2,
    "name": "mingo",
    "description": "Type de cache miniature",
    "language": "fr",
    "translation_id": null,
    "question_count": 1
  }
]
```

---

### 2. POST `/api/keyword` - Créer un nouveau mot-clé

**Objectif** : Créer un nouveau mot-clé et le retourner en JSON.

**Paramètres attendus** :
- `name` (string, requis) : Nom du mot-clé
- `language` (string, optionnel) : Code langue (défaut: 'fr')
- `description` (string, optionnel) : Description du mot-clé

**Exemple d'implémentation** :

```python
@app.route('/api/keyword', methods=['POST'])
def api_create_keyword():
    """Crée un nouveau mot-clé"""
    try:
        name = request.form.get('name', '').strip()
        language = request.form.get('language', 'fr').strip()
        description = request.form.get('description', '').strip()
        
        # Validation
        if not name:
            return jsonify({'error': 'Le nom du mot-clé est requis'}), 400
        
        # Vérifier si le mot-clé existe déjà (normalisation pour éviter doublons)
        existing = Keyword.query.filter(
            db.func.lower(db.func.replace(db.func.replace(Keyword.name, '-', ''), ' ', '')) ==
            name.lower().replace('-', '').replace(' ', '')
        ).first()
        
        if existing:
            return jsonify({
                'error': 'Un mot-clé similaire existe déjà',
                'existing_keyword': existing.to_dict()
            }), 409
        
        # Créer le nouveau mot-clé
        keyword = Keyword(
            name=name,
            language=language,
            description=description if description else None
        )
        db.session.add(keyword)
        db.session.commit()
        
        return jsonify({
            'success': True,
            'keyword': keyword.to_dict(),
            'message': f'Mot-clé "{name}" créé avec succès'
        }), 201
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
```

**Réponse attendue** :
```json
{
  "success": true,
  "keyword": {
    "id": 3,
    "name": "première cache",
    "description": null,
    "language": "fr",
    "translation_id": null,
    "question_count": 0
  },
  "message": "Mot-clé \"première cache\" créé avec succès"
}
```

---

### 3. Modifier POST `/api/question` et `/api/question/<id>` - Gérer les mots-clés

**Objectif** : Sauvegarder les mots-clés associés lors de la création/édition d'une question.

**Paramètres attendus** :
- `keywords[]` : Liste des IDs de mots-clés (peut être vide)

**Exemple de modification dans votre route existante** :

```python
@app.route('/api/question', methods=['POST'])
@app.route('/api/question/<int:question_id>', methods=['POST'])
def api_question(question_id=None):
    """Créer ou mettre à jour une question"""
    try:
        # ... votre code existant pour les autres champs ...
        
        # Gestion des mots-clés
        keyword_ids = request.form.getlist('keywords')  # Liste des IDs
        
        if question_id:
            # Édition - mettre à jour les mots-clés
            question = Question.query.get_or_404(question_id)
            
            # Vider les mots-clés existants
            question.keywords.clear()
            
            # Ajouter les nouveaux mots-clés
            if keyword_ids:
                for kw_id in keyword_ids:
                    if kw_id:  # Vérifier que l'ID n'est pas vide
                        keyword = Keyword.query.get(int(kw_id))
                        if keyword:
                            question.keywords.append(keyword)
        else:
            # Création - ajouter les mots-clés
            question = Question(...)  # Votre code de création existant
            
            # Ajouter les mots-clés
            if keyword_ids:
                for kw_id in keyword_ids:
                    if kw_id:
                        keyword = Keyword.query.get(int(kw_id))
                        if keyword:
                            question.keywords.append(keyword)
        
        db.session.commit()
        
        # ... reste de votre code ...
        
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': str(e)}), 500
```

---

### 4. Modifier GET `/question/new` et `/question/<id>/edit` - Passer les mots-clés au template

**Exemple** :

```python
@app.route('/question/new')
def question_new():
    # ... votre code existant ...
    
    return render_template('question_form.html',
        question=None,
        themes=themes,
        specific_themes=specific_themes,
        countries=countries,
        images=images
        # Les mots-clés sont chargés dynamiquement via JavaScript
    )

@app.route('/question/<int:question_id>/edit')
def question_edit(question_id):
    question = Question.query.get_or_404(question_id)
    
    # ... votre code existant ...
    
    return render_template('question_form.html',
        question=question,  # question.keywords sera disponible dans le template
        themes=themes,
        specific_themes=specific_themes,
        countries=countries,
        images=images
    )
```

---

## Fonctionnalités implémentées côté frontend

✅ **Autocomplétion intelligente**
- Recherche insensible aux accents, espaces, traits d'union
- Normalisation : "première-cache", "premiere cache", "premièrecache" → tous détectés

✅ **Création facile**
- Si le mot-clé n'existe pas, proposition de création en un clic
- Validation et ajout automatique après création

✅ **Interface intuitive**
- Tags colorés pour les mots-clés sélectionnés
- Bouton de suppression sur chaque tag
- Support du clavier (Entrée, Échap)
- Messages de confirmation

✅ **Multi-sélection**
- Une question peut avoir plusieurs mots-clés
- Les mots-clés déjà sélectionnés n'apparaissent plus dans les suggestions

---

## Tests à effectuer

### Test 1 : Chargement des mots-clés
1. Ouvrir le formulaire de création de question
2. Vérifier dans la console : `[loadAllKeywords] loaded: X keywords`
3. Taper dans le champ "Mots-clés" pour voir les suggestions

### Test 2 : Recherche avec normalisation
1. Si un mot-clé "première cache" existe
2. Taper "premiere" → doit trouver "première cache"
3. Taper "premiere-cache" → doit trouver "première cache"
4. Taper "premierecache" → doit trouver "première cache"

### Test 3 : Création d'un nouveau mot-clé
1. Taper un mot qui n'existe pas : "géocoin"
2. Cliquer sur "+ Créer : géocoin"
3. Vérifier la création en base de données
4. Le tag doit apparaître automatiquement

### Test 4 : Multi-sélection
1. Ajouter plusieurs mots-clés
2. Vérifier que les inputs hidden sont bien créés
3. Soumettre le formulaire
4. Vérifier que les mots-clés sont bien associés à la question

### Test 5 : Édition
1. Éditer une question existante avec des mots-clés
2. Les mots-clés doivent apparaître dans les tags
3. Ajouter/supprimer des mots-clés
4. Sauvegarder et vérifier la mise à jour

---

## Améliorations futures possibles

1. **Page de gestion des mots-clés** : CRUD complet pour les administrateurs
2. **Fusion de mots-clés** : Fusionner deux mots-clés similaires
3. **Statistiques** : Voir combien de questions utilisent chaque mot-clé
4. **Traductions** : Gérer les mots-clés multilingues
5. **Suggestions intelligentes** : Suggérer des mots-clés basés sur le texte de la question

---

## Dépannage

### Les suggestions ne s'affichent pas
- Vérifier que `/api/keywords/json` retourne bien du JSON
- Vérifier dans la console : `[loadAllKeywords] loaded: X keywords`
- Vérifier qu'il y a des mots-clés en base de données

### Erreur lors de la création
- Vérifier que la route `/api/keyword` existe
- Vérifier les logs serveur pour les erreurs
- Vérifier que le modèle `Keyword` est bien migré

### Les mots-clés ne sont pas sauvegardés
- Vérifier que les inputs hidden sont bien créés (inspecter le DOM)
- Vérifier que `request.form.getlist('keywords')` récupère bien les valeurs
- Vérifier que la relation many-to-many fonctionne

---

## Résumé des modifications à faire dans app.py

```python
from models import Keyword  # Ajouter l'import

# Route 1 : Liste JSON des mots-clés
@app.route('/api/keywords/json', methods=['GET'])
def api_keywords_json():
    keywords = Keyword.query.order_by(Keyword.name).all()
    return jsonify([kw.to_dict() for kw in keywords])

# Route 2 : Créer un mot-clé
@app.route('/api/keyword', methods=['POST'])
def api_create_keyword():
    name = request.form.get('name', '').strip()
    language = request.form.get('language', 'fr')
    
    if not name:
        return jsonify({'error': 'Nom requis'}), 400
    
    keyword = Keyword(name=name, language=language)
    db.session.add(keyword)
    db.session.commit()
    
    return jsonify({'success': True, 'keyword': keyword.to_dict()}), 201

# Route 3 : Modifier la gestion des questions pour inclure les keywords
# Dans votre route existante de création/édition de question :
keyword_ids = request.form.getlist('keywords')
if keyword_ids:
    question.keywords.clear()  # Si édition
    for kw_id in keyword_ids:
        if kw_id:
            keyword = Keyword.query.get(int(kw_id))
            if keyword:
                question.keywords.append(keyword)
```

Bon courage pour l'implémentation ! 🚀

