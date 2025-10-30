"""
Tests pour la génération de quiz avec gestion des keywords

Usage:
    python test_quiz_generation_keywords.py
"""

from app import app, db, _generate_quiz_playlist
from models import QuizRuleSet, Question, Keyword, UserQuestionStat, User

def test_quiz_generation_basic():
    """Test 1 : Génération basique avec keywords"""
    print("\n=== Test 1 : Génération basique ===")
    with app.app_context():
        # Trouver un QuizRuleSet existant
        rule_set = QuizRuleSet.query.first()
        
        if not rule_set:
            print("❌ Aucun QuizRuleSet trouvé. Créez-en un d'abord.")
            return
        
        print(f"QuizRuleSet : {rule_set.name}")
        print(f"prevent_duplicate_keywords : {rule_set.prevent_duplicate_keywords}")
        
        # Générer une playlist sans utilisateur (anonyme)
        playlist = _generate_quiz_playlist(rule_set, None)
        
        if playlist:
            print(f"✅ Playlist générée : {len(playlist)} questions")
            print(f"   IDs: {playlist[:5]}..." if len(playlist) > 5 else f"   IDs: {playlist}")
            
            # Vérifier que les questions existent
            questions = Question.query.filter(Question.id.in_(playlist)).all()
            print(f"✅ Toutes les questions existent : {len(questions)}/{len(playlist)}")
            
            # Vérifier les doublons de keywords si activé
            if rule_set.prevent_duplicate_keywords:
                all_keywords = set()
                duplicates = []
                
                for q in questions:
                    for kw in q.keywords:
                        if kw.id in all_keywords:
                            duplicates.append(kw.name)
                        all_keywords.add(kw.id)
                
                if duplicates:
                    print(f"⚠️ Doublons de keywords trouvés : {duplicates}")
                else:
                    print(f"✅ Aucun doublon de keyword")
        else:
            print("❌ Aucune question générée")

def test_quiz_generation_with_user():
    """Test 2 : Génération avec utilisateur connecté"""
    print("\n=== Test 2 : Génération avec utilisateur ===")
    with app.app_context():
        # Trouver un utilisateur avec historique
        user = User.query.filter(User.id > 0).first()
        rule_set = QuizRuleSet.query.first()
        
        if not user or not rule_set:
            print("⚠️ Pas d'utilisateur ou de QuizRuleSet. Test ignoré.")
            return
        
        # Compter les questions déjà répondues
        stat_count = UserQuestionStat.query.filter_by(user_id=user.id).count()
        print(f"Utilisateur : {user.username}")
        print(f"Questions déjà répondues : {stat_count}")
        
        # Générer une playlist
        playlist = _generate_quiz_playlist(rule_set, user.id)
        
        if playlist:
            print(f"✅ Playlist générée : {len(playlist)} questions")
            
            # Vérifier combien sont des nouvelles
            seen_ids = {s.question_id for s in UserQuestionStat.query.filter_by(user_id=user.id).all()}
            new_questions = [qid for qid in playlist if qid not in seen_ids]
            
            print(f"   Nouvelles questions : {len(new_questions)}/{len(playlist)}")
            if len(new_questions) < len(playlist):
                print(f"   ⚠️ {len(playlist) - len(new_questions)} questions déjà vues (compromis)")
        else:
            print("❌ Aucune question générée")

def test_keyword_stats():
    """Test 3 : Statistiques sur les keywords"""
    print("\n=== Test 3 : Statistiques keywords ===")
    with app.app_context():
        # Compter les questions avec/sans keywords
        total_questions = Question.query.filter_by(is_published=True).count()
        
        # Questions avec au moins un keyword
        questions_with_keywords = db.session.query(Question).join(
            Question.keywords
        ).filter(Question.is_published == True).distinct().count()
        
        questions_without_keywords = total_questions - questions_with_keywords
        
        print(f"Questions publiées : {total_questions}")
        print(f"  - Avec keywords : {questions_with_keywords}")
        print(f"  - Sans keywords : {questions_without_keywords}")
        
        # Keywords les plus utilisés
        from sqlalchemy import func, select
        result = db.session.query(
            Keyword.name,
            func.count(db.literal_column('question_id')).label('count')
        ).select_from(
            db.text('question_keywords')
        ).join(
            Keyword,
            Keyword.id == db.literal_column('keyword_id')
        ).group_by(
            Keyword.name
        ).order_by(
            func.count(db.literal_column('question_id')).desc()
        ).limit(10).all()
        
        if result:
            print(f"\nTop 10 keywords les plus utilisés :")
            for name, count in result:
                print(f"  - {name}: {count} questions")
        else:
            print("\nAucun keyword utilisé")

def test_prevent_duplicate_keywords():
    """Test 4 : Vérifier prevent_duplicate_keywords"""
    print("\n=== Test 4 : Prévention doublons keywords ===")
    with app.app_context():
        rule_set = QuizRuleSet.query.first()
        
        if not rule_set:
            print("⚠️ Aucun QuizRuleSet. Test ignoré.")
            return
        
        # Sauvegarder la valeur actuelle
        original_value = rule_set.prevent_duplicate_keywords
        
        # Test AVEC prévention
        rule_set.prevent_duplicate_keywords = True
        print(f"Test AVEC prévention (prevent_duplicate_keywords = True)")
        playlist_with = _generate_quiz_playlist(rule_set, None)
        
        # Compter les keywords uniques
        if playlist_with:
            questions = Question.query.filter(Question.id.in_(playlist_with)).all()
            keywords_with = set()
            for q in questions:
                for kw in q.keywords:
                    keywords_with.add(kw.id)
            print(f"  Playlist: {len(playlist_with)} questions, {len(keywords_with)} keywords uniques")
        
        # Test SANS prévention
        rule_set.prevent_duplicate_keywords = False
        print(f"\nTest SANS prévention (prevent_duplicate_keywords = False)")
        playlist_without = _generate_quiz_playlist(rule_set, None)
        
        # Compter les keywords (peut y avoir des doublons maintenant)
        if playlist_without:
            questions = Question.query.filter(Question.id.in_(playlist_without)).all()
            keywords_without = []
            for q in questions:
                for kw in q.keywords:
                    keywords_without.append(kw.id)
            unique_keywords = len(set(keywords_without))
            print(f"  Playlist: {len(playlist_without)} questions, {len(keywords_without)} keywords total, {unique_keywords} uniques")
        
        # Restaurer
        rule_set.prevent_duplicate_keywords = original_value
        
        print(f"\n✅ Test terminé. Valeur restaurée: {original_value}")

def test_all():
    """Exécuter tous les tests"""
    print("=" * 70)
    print("Tests de génération de quiz avec keywords")
    print("=" * 70)
    
    try:
        test_quiz_generation_basic()
        test_quiz_generation_with_user()
        test_keyword_stats()
        test_prevent_duplicate_keywords()
        
        print("\n" + "=" * 70)
        print("✅ Tous les tests sont terminés !")
        print("=" * 70)
        print("\n💡 Consultez les logs ci-dessus pour voir les détails de génération")
        print("   Les logs [QUIZ PLAYLIST] montrent la logique en action\n")
        
    except Exception as e:
        print(f"\n❌ Erreur lors des tests : {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_all()

