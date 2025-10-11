# 📖 Guide d'utilisation - Quiz Géocaching

## 🏁 Premiers pas

### Installation et lancement

1. **Installer les dépendances Python :**
   ```bash
   pip install -r requirements.txt
   ```

2. **Initialiser la base de données avec des exemples :**
   ```bash
   python init_db.py
   ```
   Cette commande crée la base de données et ajoute 3 questions d'exemple.

3. **Lancer l'application :**
   ```bash
   python app.py
   ```

4. **Accéder à l'interface :**
   Ouvrez votre navigateur et allez à : `http://localhost:5000`

---

## 🎨 Interface principale

L'interface se compose de :

- **Barre de recherche** : Recherchez des questions en temps réel
- **Bouton "+ Nouvelle Question"** : Ouvre le formulaire de création
- **Grille de questions** : Affiche toutes vos questions sous forme de cartes

### Les cartes de questions

Chaque carte affiche :
- 🏷️ **Badges** : Thématique, niveau de difficulté, statut de publication
- 📝 **Texte de la question**
- 👤 **Auteur**
- 💡 **Indice** (si présent)
- 🌍 **Pays** (si spécifié)
- ✅ **Réponses possibles** avec la bonne réponse en vert
- 📖 **Explication détaillée**
- 📅 **Dates** de création et modification
- 📊 **Statistiques** de réussite (si disponibles)
- ✏️ **Bouton d'édition**
- 🗑️ **Bouton de suppression**

---

## ➕ Créer une nouvelle question

1. Cliquez sur **"+ Nouvelle Question"**
2. Une fenêtre modale s'ouvre avec le formulaire

### Champs obligatoires (marqués *)

- **Auteur** : Votre nom ou pseudo
- **Question** : Le texte de la question
- **Réponses possibles** : Minimum 2 réponses (4 par défaut)
- **Bonne réponse** : Le numéro de la bonne réponse (1, 2, 3, etc.)

### Champs optionnels

- **URL image pour les réponses** : Ajoutez des images aux réponses
- **Explication détaillée** : Contexte et explications pour la réponse
- **Indice** : Un indice pour aider les joueurs
- **Thématique large** : Catégorie générale (ex: "Règles", "Histoire", "Technique")
- **Thématique précise** : Sous-catégorie (ex: "Reviewers", "Types de caches", "GPS")
- **Pays spécifique** : Pour des questions liées à un pays particulier
- **Niveau de difficulté** : De 1 (Très facile) à 5 (Très difficile)
- **ID de traduction** : Pour lier une traduction de cette question
- **Question en ligne** : Cochez pour publier la question

### Ajouter plus de réponses

- Cliquez sur **"+ Ajouter une réponse"** pour ajouter autant de réponses que nécessaire
- Les 4 premières réponses sont affichées par défaut

---

## ✏️ Éditer une question

1. Cliquez sur l'icône **✏️** sur la carte de la question
2. Le formulaire s'ouvre avec les données actuelles
3. Modifiez les champs souhaités
4. Cliquez sur **"Mettre à jour"**

Les statistiques (nombre de réponses et taux de réussite) sont affichées en bas du formulaire pour information.

---

## 🗑️ Supprimer une question

1. Cliquez sur l'icône **🗑️** sur la carte de la question
2. Confirmez la suppression dans la boîte de dialogue
3. La question est supprimée définitivement

⚠️ **Attention** : Cette action est irréversible !

---

## 🔍 Rechercher des questions

La barre de recherche en haut de la page permet de filtrer les questions en temps réel.

**Recherche dans :**
- Le texte de la question
- L'auteur
- La thématique large
- La thématique précise

La recherche se met à jour automatiquement pendant que vous tapez (délai de 500ms).

---

## 🌍 Système de traductions

Le système de traductions permet de lier des questions dans différentes langues.

### Comment ça marche ?

1. **Créez la question principale** dans votre langue
   - Notez son ID (visible dans l'URL ou en bas de la carte)

2. **Créez la traduction**
   - Créez une nouvelle question dans une autre langue
   - Dans le champ "ID de traduction", entrez l'ID de la question originale

3. **Avantages**
   - Comparez les taux de réussite selon les langues/pays
   - Facilitez la gestion multilingue
   - Maintenez la cohérence entre versions

### Exemple

Question en français (ID: 1) → Traduction anglaise (ID: 2, translation_id: 1)
Question anglaise (ID: 3) → Traduction française (ID: 4, translation_id: 3)

---

## 📊 Niveaux de difficulté

- **Niveau 1** : Très facile - Questions basiques pour débutants
- **Niveau 2** : Facile - Questions simples
- **Niveau 3** : Moyen - Questions standard
- **Niveau 4** : Difficile - Connaissances approfondies requises
- **Niveau 5** : Très difficile - Pour experts uniquement

---

## 🎯 Organisation par thématiques

### Thématiques larges (exemples)

- **Règles** : Règles officielles du géocaching
- **Histoire** : Histoire du géocaching
- **Technique** : GPS, cartes, navigation
- **Types de caches** : Traditionnelles, Mystery, Multi-caches, etc.
- **Communauté** : Events, méga-events, culture
- **Statistiques** : Chiffres et données

### Thématiques précises (exemples)

- **Reviewers** : Questions sur les reviewers
- **Tailles** : Tailles des caches
- **Acronymes** : FTF, DNF, TFTC, etc.
- **GPS** : Technologie GPS
- **Attributs** : Attributs des caches
- **Pays spécifiques** : Règles ou stats par pays

💡 **Astuce** : Utilisez la thématique précise pour éviter de poser deux fois des questions similaires avec des niveaux de difficulté différents.

---

## 🎲 Réponses avec images

Vous pouvez ajouter des images aux réponses en fournissant des URLs.

### Format supporté

- Les URLs doivent pointer vers des images accessibles en ligne
- Formats supportés : JPG, PNG, GIF, WEBP
- Exemples d'hébergement : Imgur, votre propre serveur, etc.

### Utilisation

1. Dans le formulaire, remplissez le champ "URL image" à côté de chaque réponse
2. Les images seront affichées lors du quiz (dans une future version)
3. Laissez vide si pas d'image pour cette réponse

---

## 📈 Statistiques

Les statistiques sont automatiquement suivies (dans une future version avec le quiz) :

- **Taux de réussite** : Pourcentage de bonnes réponses
- **Nombre de réponses** : Combien de fois la question a été posée

Ces données vous aident à :
- Identifier les questions trop faciles ou trop difficiles
- Ajuster les niveaux de difficulté
- Améliorer les formulations

---

## 🔧 Configuration avancée

### Changer la base de données

Par défaut, l'application utilise SQLite. Pour utiliser une autre base de données :

1. Modifiez `config.py` :
   ```python
   # PostgreSQL
   SQLALCHEMY_DATABASE_URI = 'postgresql://user:pass@localhost/geocaching_quiz'
   
   # MySQL
   SQLALCHEMY_DATABASE_URI = 'mysql://user:pass@localhost/geocaching_quiz'
   ```

2. Installez le driver approprié :
   ```bash
   # PostgreSQL
   pip install psycopg2-binary
   
   # MySQL
   pip install mysqlclient
   ```

### Personnaliser le port

Dans `app.py`, modifiez la dernière ligne :
```python
app.run(debug=True, host='0.0.0.0', port=8080)  # Exemple avec le port 8080
```

---

## 💾 Sauvegarde et restauration

### Sauvegarder la base de données

La base de données SQLite est un simple fichier : `geocaching_quiz.db`

Pour sauvegarder :
```bash
# Copier le fichier
copy geocaching_quiz.db geocaching_quiz_backup.db

# Ou avec la date
copy geocaching_quiz.db geocaching_quiz_backup_2025-10-11.db
```

### Restaurer une sauvegarde

```bash
# Restaurer depuis une sauvegarde
copy geocaching_quiz_backup.db geocaching_quiz.db
```

---

## 🎓 Astuces et bonnes pratiques

### ✅ Bonnes pratiques

1. **Soyez précis** : Rédigez des questions claires et sans ambiguïté
2. **Utilisez les thématiques** : Organisez bien vos questions pour faciliter la gestion
3. **Ajoutez des explications** : Aidez les joueurs à apprendre avec des réponses détaillées
4. **Testez vos questions** : Vérifiez que la bonne réponse est correcte !
5. **Utilisez les niveaux** : Classez correctement la difficulté
6. **Brouillon d'abord** : Ne publiez pas immédiatement, relisez avant

### 📝 Conseils de rédaction

- **Question claire** : Évitez les formulations ambiguës
- **Réponses plausibles** : Toutes les réponses doivent sembler possibles
- **Longueur équilibrée** : Les réponses doivent avoir des longueurs similaires
- **Une seule bonne réponse** : Évitez les questions à réponses multiples pour l'instant

### 🌟 Idées de questions

- Questions sur les règles officielles
- Questions historiques (création du géocaching, évolution)
- Questions sur les types de caches
- Questions sur la terminologie (FTF, DNF, TFTC, etc.)
- Questions sur les statistiques mondiales
- Questions pays-spécifiques (reviewers, règles locales)
- Questions techniques (GPS, coordonnées)
- Questions sur les events et méga-events

---

## ❓ FAQ

**Q : Puis-je importer des questions depuis un fichier Excel/CSV ?**  
R : Pas encore, mais c'est prévu dans les futures versions.

**Q : Comment supprimer toutes les questions ?**  
R : Supprimez le fichier `geocaching_quiz.db` et relancez `python init_db.py`.

**Q : Les statistiques se mettent-elles à jour automatiquement ?**  
R : Les statistiques seront mises à jour quand la partie quiz sera développée.

**Q : Puis-je avoir plusieurs utilisateurs avec des permissions différentes ?**  
R : Pas encore, mais un système d'authentification est prévu.

**Q : Comment exporter mes questions ?**  
R : Pour l'instant, la base SQLite peut être copiée. Un export JSON/CSV est prévu.

---

## 🆘 Problèmes courants

### L'application ne démarre pas

1. Vérifiez que toutes les dépendances sont installées : `pip install -r requirements.txt`
2. Vérifiez que Python 3.7+ est installé
3. Vérifiez les messages d'erreur dans la console

### Les modifications ne s'affichent pas

1. Rafraîchissez la page avec Ctrl+F5
2. Vérifiez que la base de données n'est pas en lecture seule

### Erreur "Table already exists"

C'est normal si vous relancez `init_db.py` alors que la base existe. Répondez 'n' ou supprimez `geocaching_quiz.db` d'abord.

---

## 📞 Support

Pour toute question ou suggestion, n'hésitez pas à ouvrir une issue sur le projet ou à contribuer avec vos améliorations !

Bon géocaching ! 🗺️🎯

