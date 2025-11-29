import os
import smtplib
from email.mime.text import MIMEText
import logging

# Configuration du logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def _smtp_configured():
    return bool(os.environ.get('MAIL_SERVER'))


def send_email_optional(to_email: str, subject: str, body: str):
    """
    Envoie un email si la configuration SMTP est présente.
    En cas d'erreur ou d'absence de configuration, log le contenu dans la console.
    """
    print(f"[EMAIL] Tentative envoi email à {to_email}, sujet: {subject}")
    if not _smtp_configured():
        print(f"[EMAIL] Configuration SMTP manquante, email NON envoyé")
        return
    print(f"[EMAIL] Configuration SMTP OK, envoi en cours...")
    if not _smtp_configured():
        logger.info(f"SMTP non configuré. Email simulé vers {to_email}:\nSujet: {subject}\nCorps:\n{body}")
        return

    server = os.environ.get('MAIL_SERVER')
    port = int(os.environ.get('MAIL_PORT') or 587)
    username = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    use_tls = os.environ.get('MAIL_USE_TLS', '1') == '1'
    default_sender = os.environ.get('MAIL_DEFAULT_SENDER') or username

    if not (server and default_sender):
        logger.info(f"Configuration SMTP incomplète. Email simulé vers {to_email}:\nSujet: {subject}\nCorps:\n{body}")
        return

    msg = MIMEText(body, _charset='utf-8')
    msg['Subject'] = subject
    msg['From'] = default_sender
    msg['To'] = to_email

    try:
        # Utiliser SSL direct pour le port 465, sinon SMTP avec starttls
        if port == 465:
            smtp = smtplib.SMTP_SSL(server, port)
        else:
            smtp = smtplib.SMTP(server, port)
            try:
                if use_tls:
                    smtp.starttls()
            except Exception as e:
                logger.warning(f"Erreur lors du STARTTLS: {e}")

        if username and password:
            smtp.login(username, password)
        
        smtp.sendmail(default_sender, [to_email], msg.as_string())
        print(f"[EMAIL] Email envoyé avec succès à {to_email}")

        try:
            smtp.quit()
        except Exception:
            pass
            
    except Exception as e:
        print(f"[EMAIL] ERREUR lors de l'envoi: {e}")
        logger.error(f"Erreur lors de l'envoi de l'email: {e}")
        logger.info(f"--- EMAIL CONTENU (FALLBACK) ---\nVers: {to_email}\nSujet: {subject}\nCorps:\n{body}\n--------------------------------")
