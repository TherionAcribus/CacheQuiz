"""
Tests rapides pour vérifier que le système de mots-clés fonctionne

Usage:
    python test_keywords_quick.py
"""

from app import app, db
from models import Keyword, Question

def test_keyword_creation():
    """Test 1 : Créer un mot-clé"""
    print("\n=== Test 1 : Création d'un mot-clé ===")
    with app.app_context():
        # Créer un mot-clé de test
        keyword = Keyword(name="test_keyword", language="fr", description="Test")
        db.session.add(keyword)
        db.session.commit()
        
        # Vérifier qu'il existe
        found = Keyword.query.filter_by(name="test_keyword").first()
        if found:
            print(f"✅ Mot-clé créé : {found.name} (ID: {found.id})")
            
            # Nettoyer
            db.session.delete(found)
            db.session.commit()
            print("✅ Mot-clé supprimé (nettoyage)")
        else:
            print("❌ Échec : Mot-clé non trouvé")

def test_keyword_model():
    """Test 2 : Vérifier les méthodes du modèle"""
    print("\n=== Test 2 : Méthodes du modèle Keyword ===")
    with app.app_context():
        keyword = Keyword(name="mingo", language="fr", description="Cache miniature")
        db.session.add(keyword)
        db.session.commit()
        
        # Test to_dict()
        data = keyword.to_dict()
        if 'id' in data and 'name' in data and data['name'] == 'mingo':
            print(f"✅ to_dict() fonctionne : {data}")
        else:
            print(f"❌ to_dict() échoue : {data}")
        
        # Nettoyer
        db.session.delete(keyword)
        db.session.commit()

def test_question_keyword_relation():
    """Test 3 : Association Question ↔ Keyword"""
    print("\n=== Test 3 : Relation Question ↔ Keyword ===")
    with app.app_context():
        # Créer un mot-clé
        keyword1 = Keyword(name="test_relation_1", language="fr")
        keyword2 = Keyword(name="test_relation_2", language="fr")
        db.session.add(keyword1)
        db.session.add(keyword2)
        db.session.flush()
        
        # Trouver une question existante ou créer une question de test
        question = Question.query.first()
        if not question:
            print("⚠️  Aucune question existante, impossible de tester la relation")
            db.session.rollback()
            return
        
        # Sauvegarder les mots-clés actuels pour les restaurer
        original_keywords = list(question.keywords)
        
        # Associer les mots-clés
        question.keywords.append(keyword1)
        question.keywords.append(keyword2)
        db.session.commit()
        
        # Vérifier l'association
        question = Question.query.get(question.id)
        if keyword1 in question.keywords and keyword2 in question.keywords:
            print(f"✅ Association réussie : Question {question.id} a {len(question.keywords)} mots-clés")
            
            # Vérifier to_dict()
            data = question.to_dict()
            if 'keywords' in data and len(data['keywords']) >= 2:
                print(f"✅ to_dict() inclut les keywords : {[k['name'] for k in data['keywords']]}")
            else:
                print(f"❌ to_dict() n'inclut pas les keywords correctement")
        else:
            print("❌ Association échouée")
        
        # Restaurer l'état original
        question.keywords = original_keywords
        db.session.delete(keyword1)
        db.session.delete(keyword2)
        db.session.commit()
        print("✅ Données restaurées (nettoyage)")

def test_database_tables():
    """Test 4 : Vérifier que les tables existent"""
    print("\n=== Test 4 : Vérification des tables ===")
    with app.app_context():
        try:
            # Tester la table keywords
            count = db.session.query(Keyword).count()
            print(f"✅ Table 'keywords' existe : {count} enregistrement(s)")
            
            # Tester la table d'association question_keywords
            result = db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table' AND name='question_keywords'"))
            if result.fetchone():
                print("✅ Table d'association 'question_keywords' existe")
            else:
                print("❌ Table 'question_keywords' n'existe pas")
            
            # Tester la table d'association quiz_rule_set_keywords
            result = db.session.execute(db.text("SELECT name FROM sqlite_master WHERE type='table' AND name='quiz_rule_set_keywords'"))
            if result.fetchone():
                print("✅ Table d'association 'quiz_rule_set_keywords' existe")
            else:
                print("❌ Table 'quiz_rule_set_keywords' n'existe pas")
                
        except Exception as e:
            print(f"❌ Erreur : {e}")

def test_all():
    """Exécuter tous les tests"""
    print("=" * 70)
    print("Tests rapides du système de mots-clés")
    print("=" * 70)
    
    try:
        test_database_tables()
        test_keyword_creation()
        test_keyword_model()
        test_question_keyword_relation()
        
        print("\n" + "=" * 70)
        print("✅ Tous les tests sont terminés !")
        print("=" * 70)
        print("\n💡 Prochaine étape : Ouvrir l'application et tester manuellement")
        print("   1. Ouvrir le formulaire de création de question")
        print("   2. Taper dans le champ 'Mots-clés'")
        print("   3. Créer un nouveau mot-clé")
        print("   4. Sauvegarder la question")
        print()
        
    except Exception as e:
        print(f"\n❌ Erreur lors des tests : {e}")
        import traceback
        traceback.print_exc()

if __name__ == '__main__':
    test_all()

