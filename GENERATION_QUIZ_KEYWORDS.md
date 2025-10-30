# Génération de Quiz avec Gestion Intelligente des Keywords

## 🎯 Vue d'ensemble

Le système de génération de quiz a été amélioré pour gérer intelligemment les **keywords** (mots-clés) et éviter les doublons de sujets, tout en respectant un ordre de priorités strict.

---

## 📊 Ordre de Priorités

La génération de quiz respecte les priorités suivantes (par ordre d'importance) :

### 1️⃣ **Conditions du QuizRuleSet** (ABSOLU - jamais contourné)
- Thèmes larges autorisés
- Sous-thèmes autorisés  
- Difficultés autorisées
- Quotas par difficulté
- Questions publiées uniquement

### 2️⃣ **Pas de doublons de keywords** (si `prevent_duplicate_keywords = True`)
- Une seule question par keyword dans le quiz
- Exemple : Si 2 questions ont le keyword "première cache", une seule sera sélectionnée

### 3️⃣ **Pas de questions déjà répondues**
- Priorité aux questions non vues par l'utilisateur
- Améliore l'expérience en proposant du nouveau contenu

### 4️⃣ **Pas de keywords déjà répondus**
- Évite de proposer des questions sur des sujets déjà maîtrisés
- Exemple : Si l'utilisateur a déjà répondu sur "première cache", on évitera d'autres questions avec ce keyword

---

## 🔧 Fonctionnement Technique

### Algorithme de Sélection

```python
Pour chaque difficulté requise:
    1. Récupérer toutes les questions candidates (selon conditions QuizRuleSet)
    2. Charger les keywords de chaque question candidate
    3. Scorer chaque question selon les priorités:
       - Score priorité 1: Pas de doublon keyword ✅
       - Score priorité 2: Question non vue ✅
       - Score priorité 3: Keyword non répondu ✅
       - Score bonus: Pas de keyword (aucun risque de doublon)
    4. Trier les questions du meilleur au pire score
    5. Sélectionner jusqu'au quota requis
    6. Marquer les keywords utilisés pour éviter les doublons
```

### Fonction Principale

**`_generate_quiz_playlist(rule_set, current_user_id)`**

Génère la playlist complète du quiz en respectant toutes les priorités.

**Paramètres** :
- `rule_set` : Les règles du quiz (QuizRuleSet)
- `current_user_id` : ID de l'utilisateur (ou None si anonyme)

**Retour** :
- Liste d'IDs de questions ordonnées

### Fonctions Auxiliaires

#### `_get_user_answered_keywords(user_id)`
Récupère tous les keywords des questions déjà répondues par l'utilisateur.

#### `_select_questions_with_keyword_logic(...)`
Applique la logique de sélection avec gestion des keywords sur un pool de questions.

**Retourne** :
- `selected_ids` : Questions sélectionnées
- `used_keywords` : Keywords utilisés (mis à jour)
- `stats` : Statistiques de sélection (conditions parfaites ou compromis)

---

## 📝 Logs de Debug

Le système produit des logs détaillés pour faciliter le debug :

### Exemple de Log - Conditions Parfaites ✅

```
[QUIZ PLAYLIST] === Génération playlist pour Quiz Géocaching Débutant ===
[QUIZ PLAYLIST] Utilisateur 5: 12 questions vues, 8 keywords répondus
[QUIZ PLAYLIST] Prévention doublons keywords: OUI
[QUIZ PLAYLIST] Mode AUTO: difficultés [1, 2, 3], quotas {'1': 3, '2': 4, '3': 3}

[QUIZ PLAYLIST] Difficulté 1: quota=3
[QUIZ PLAYLIST]   Candidats disponibles: 45
[QUIZ PLAYLIST]   Sélectionnés: 3/3

[QUIZ PLAYLIST] Difficulté 2: quota=4
[QUIZ PLAYLIST]   Candidats disponibles: 38
[QUIZ PLAYLIST]   Sélectionnés: 4/4

[QUIZ PLAYLIST] Difficulté 3: quota=3
[QUIZ PLAYLIST]   Candidats disponibles: 25
[QUIZ PLAYLIST]   Sélectionnés: 3/3

[QUIZ PLAYLIST] === RÉSUMÉ FINAL ===
[QUIZ PLAYLIST] Playlist générée: 10/10 questions
[QUIZ PLAYLIST] ✅ CONDITIONS PARFAITES pour toutes les questions !
[QUIZ PLAYLIST] Keywords uniques utilisés: 7
[QUIZ PLAYLIST] ==================
```

### Exemple de Log - Avec Compromis ⚠️

```
[QUIZ PLAYLIST] === Génération playlist pour Quiz Géocaching Expert ===
[QUIZ PLAYLIST] Utilisateur 12: 150 questions vues, 45 keywords répondus
[QUIZ PLAYLIST] Prévention doublons keywords: OUI
[QUIZ PLAYLIST] Mode AUTO: difficultés [4, 5], quotas {'4': 5, '5': 5}

[QUIZ PLAYLIST] Difficulté 4: quota=5
[QUIZ PLAYLIST]   Candidats disponibles: 15
[QUIZ PLAYLIST]   Sélectionnés: 5/5
[QUIZ PLAYLIST]     ⚠️ 2x question already seen
[QUIZ PLAYLIST]     ⚠️ 1x keyword already answered

[QUIZ PLAYLIST] Difficulté 5: quota=5
[QUIZ PLAYLIST]   Candidats disponibles: 8
[QUIZ PLAYLIST]   Sélectionnés: 5/5
[QUIZ PLAYLIST]     ⚠️ 3x question already seen
[QUIZ PLAYLIST]     ⚠️ 2x keyword already answered

[QUIZ PLAYLIST] === RÉSUMÉ FINAL ===
[QUIZ PLAYLIST] Playlist générée: 10/10 questions
[QUIZ PLAYLIST] ⚠️ COMPROMIS NÉCESSAIRES:
[QUIZ PLAYLIST]   Difficulté 4: ⚠️ 2x question already seen, ⚠️ 1x keyword already answered
[QUIZ PLAYLIST]   Difficulté 5: ⚠️ 3x question already seen, ⚠️ 2x keyword already answered
[QUIZ PLAYLIST] Keywords uniques utilisés: 8
[QUIZ PLAYLIST] ==================
```

---

## 🎮 Modes de Fonctionnement

### Mode AUTO (par défaut)

Sélection automatique avec quotas par difficulté.

**Processus** :
1. Pour chaque difficulté avec quota > 0
2. Filtrer selon thèmes/sous-thèmes du QuizRuleSet
3. Appliquer la logique keywords
4. Intercaler les questions pour varier les difficultés

### Mode MANUAL

Sélection parmi une liste prédéfinie de questions.

**Processus** :
1. Partir des questions sélectionnées manuellement
2. Filtrer les questions non publiées
3. Appliquer la logique keywords sur tout le pool
4. Retourner la playlist ordonnée

---

## ⚙️ Configuration dans QuizRuleSet

### Paramètre `prevent_duplicate_keywords`

**Type** : Boolean  
**Défaut** : `True`  
**Description** : Active ou désactive la prévention des doublons de keywords

```python
# Activer la prévention (recommandé)
rule_set.prevent_duplicate_keywords = True

# Désactiver (permet plusieurs questions avec même keyword)
rule_set.prevent_duplicate_keywords = False
```

### Paramètre `use_all_keywords`

**Type** : Boolean  
**Défaut** : `True`  
**Description** : Utiliser tous les keywords ou filtrer par liste

```python
# Utiliser tous les keywords
rule_set.use_all_keywords = True

# Filtrer par liste spécifique (à implémenter dans le futur)
rule_set.use_all_keywords = False
rule_set.allowed_keywords = [keyword1, keyword2, ...]
```

---

## 📈 Exemples d'Utilisation

### Exemple 1 : Quiz Débutant

**Configuration** :
- 10 questions
- Difficultés 1-3
- `prevent_duplicate_keywords = True`
- Pool : 150 questions disponibles
- Utilisateur : 5 questions déjà vues, 3 keywords répondus

**Résultat** :
```
✅ CONDITIONS PARFAITES
- 0 doublons de keywords
- 10 questions non vues
- 0 keywords déjà répondus
```

### Exemple 2 : Quiz Expert (Pool Limité)

**Configuration** :
- 15 questions
- Difficultés 4-5
- `prevent_duplicate_keywords = True`
- Pool : 20 questions disponibles
- Utilisateur : 18 questions déjà vues, 12 keywords répondus

**Résultat** :
```
⚠️ COMPROMIS NÉCESSAIRES
- 0 doublons de keywords (priorité respectée)
- 13/15 questions non vues (2 déjà vues par manque de pool)
- 10/15 sans keyword répondu (5 avec keyword déjà répondu)
```

### Exemple 3 : Quiz Sans Keywords

**Configuration** :
- 8 questions
- Questions sans keywords assignés
- `prevent_duplicate_keywords = True`

**Résultat** :
```
✅ CONDITIONS PARFAITES
- Pas de keywords → pas de risque de doublon
- Sélection basée sur questions vues/non vues
```

---

## 🔍 Cas Particuliers

### Questions Sans Keywords

Les questions sans keywords sont **prioritaires** car elles ne risquent pas de créer de doublons.

**Avantage** : Dans un quiz avec peu de pool, les questions sans keywords seront toujours sélectionnées en premier.

### Plusieurs Keywords par Question

Une question peut avoir plusieurs keywords. Elle sera exclue si **au moins un** de ses keywords est déjà utilisé dans le quiz.

**Exemple** :
```python
Question 1: keywords = ["première cache", "Dave Ulmer"]
Question 2: keywords = ["Dave Ulmer", "Oregon"]

# Si Question 1 est sélectionnée en premier
# → Question 2 sera exclue (doublon sur "Dave Ulmer")
```

### Pool Insuffisant

Quand le pool est insuffisant pour respecter toutes les conditions, le système fait des compromis **dans l'ordre inverse des priorités** :

1. ✅ Toujours respecter les conditions QuizRuleSet
2. ✅ Toujours éviter les doublons de keywords (si activé)
3. ⚠️ Accepter des questions déjà vues si nécessaire
4. ⚠️ Accepter des keywords déjà répondus si nécessaire

---

## 🛠️ Dépannage

### Aucune question sélectionnée

**Symptôme** : Playlist vide malgré des questions disponibles

**Causes possibles** :
1. Aucune question publiée dans le pool
2. Conditions QuizRuleSet trop restrictives
3. Toutes les questions ont des keywords en doublon

**Solution** :
- Vérifier les logs : `[QUIZ PLAYLIST] Candidats disponibles: X`
- Assouplir les conditions du QuizRuleSet
- Désactiver temporairement `prevent_duplicate_keywords`

### Trop de compromis

**Symptôme** : Beaucoup de questions déjà vues ou keywords répondus

**Causes possibles** :
1. Pool de questions trop petit
2. Utilisateur a déjà beaucoup répondu
3. Trop de keywords en commun entre questions

**Solutions** :
- Ajouter plus de questions au pool
- Diversifier les keywords
- Ajuster les quotas par difficulté

### Logs non affichés

**Symptôme** : Pas de logs dans la console

**Solution** :
```python
# S'assurer que les logs Flask sont activés
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## 🚀 Améliorations Futures

### Implémentées ✅

- [x] Gestion des keywords dans la génération
- [x] Priorités multiples avec fallback
- [x] Logs détaillés pour debug
- [x] Support mode AUTO et MANUAL
- [x] Prévention doublons keywords

### À Implémenter 🔜

- [ ] **Filtrage par keywords autorisés** : Utiliser `use_all_keywords = False` pour ne sélectionner que certains keywords
- [ ] **Pondération des priorités** : Permettre de configurer l'importance relative de chaque priorité
- [ ] **Statistiques temps réel** : Afficher les stats de sélection dans l'interface
- [ ] **Suggestion intelligente** : Proposer des questions basées sur les keywords faibles de l'utilisateur
- [ ] **Mode apprentissage** : Répéter les keywords mal maîtrisés

---

## 📚 Références

### Fichiers Modifiés

- `app.py` : Fonctions de génération de playlist
  - `_generate_quiz_playlist()` : Fonction principale
  - `_select_questions_with_keyword_logic()` : Logique de sélection
  - `_get_user_answered_keywords()` : Récupération keywords répondus

### Modèles Utilisés

- `QuizRuleSet` : Configuration du quiz
- `Question` : Questions avec keywords
- `Keyword` : Mots-clés
- `UserQuestionStat` : Historique utilisateur

### Documentation Associée

- `KEYWORDS_GUIDE.md` : Guide des keywords
- `IMPLEMENTATION_COMPLETE.md` : Implémentation complète
- `MODES_SELECTION_QUESTIONS.md` : Modes de sélection

---

## ✅ Validation

Le système a été testé avec succès sur :

- ✅ Pool large avec conditions parfaites
- ✅ Pool limité avec compromis nécessaires
- ✅ Mode AUTO et MANUAL
- ✅ Utilisateurs avec historique varié
- ✅ Questions avec et sans keywords
- ✅ Désactivation de `prevent_duplicate_keywords`

**Prêt pour la production ! 🎉**

