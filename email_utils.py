import os
import smtplib
from email.mime.text import MIMEText


def _smtp_configured():
    return bool(os.environ.get('MAIL_SERVER'))


def send_email_optional(to_email: str, subject: str, body: str):
    """
    Envoie un email si la configuration SMTP est présente, sinon ne fait rien.
    """
    if not _smtp_configured():
        return

    server = os.environ.get('MAIL_SERVER')
    port = int(os.environ.get('MAIL_PORT') or 587)
    username = os.environ.get('MAIL_USERNAME')
    password = os.environ.get('MAIL_PASSWORD')
    use_tls = os.environ.get('MAIL_USE_TLS', '1') == '1'
    default_sender = os.environ.get('MAIL_DEFAULT_SENDER') or username

    if not (server and default_sender):
        return

    msg = MIMEText(body, _charset='utf-8')
    msg['Subject'] = subject
    msg['From'] = default_sender
    msg['To'] = to_email

    smtp = smtplib.SMTP(server, port)
    try:
        if use_tls:
            smtp.starttls()
        if username and password:
            smtp.login(username, password)
        smtp.sendmail(default_sender, [to_email], msg.as_string())
    finally:
        try:
            smtp.quit()
        except Exception:
            pass


