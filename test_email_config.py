import os
import smtplib
from email.mime.text import MIMEText
from dotenv import load_dotenv

# Charger les variables d'environnement (.env)
load_dotenv()

def test_smtp_connection():
    print("--- Test de Configuration SMTP ---")
    
    server = os.environ.get('MAIL_SERVER')
    port_str = os.environ.get('MAIL_PORT')
    username = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    use_tls = os.environ.get('MAIL_USE_TLS', '1') == '1'
    sender = os.environ.get('MAIL_DEFAULT_SENDER') or username
    
    print(f"Serveur: {server}")
    print(f"Port: {port_str}")
    print(f"Utilisateur: {username}")
    print(f"Expéditeur: {sender}")
    print(f"TLS activé: {use_tls}")
    print(f"Mot de passe configuré: {'OUI' if password else 'NON'}")
    
    if not (server and port_str and username and password):
        print("\n❌ ERREUR: Configuration incomplète. Vérifiez votre fichier .env ou vos variables d'environnement.")
        return

    try:
        port = int(port_str)
        print(f"\nTentative de connexion à {server}:{port}...")
        
        smtp = None
        if port == 465:
            print("Utilisation de SMTP_SSL...")
            smtp = smtplib.SMTP_SSL(server, port)
        else:
            print("Utilisation de SMTP standard...")
            smtp = smtplib.SMTP(server, port)
            if use_tls:
                print("Démarrage de TLS...")
                smtp.starttls()
        
        print(f"Authentification en tant que {username}...")
        smtp.login(username, password)
        print("✅ Authentification réussie !")
        
        # Test d'envoi
        to_email = input("\nEntrez une adresse email pour recevoir un test (ou tapez Entrée pour ignorer): ").strip()
        if to_email:
            msg = MIMEText("Ceci est un email de test pour vérifier la configuration SMTP.", _charset='utf-8')
            msg['Subject'] = "Test de configuration SMTP - CacheQuiz"
            msg['From'] = sender
            msg['To'] = to_email
            
            print(f"Envoi de l'email à {to_email}...")
            smtp.sendmail(sender, [to_email], msg.as_string())
            print("✅ Email envoyé avec succès !")
        
        smtp.quit()
        print("\nTest terminé avec succès.")
        
    except Exception as e:
        print(f"\n❌ ERREUR: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_smtp_connection()

