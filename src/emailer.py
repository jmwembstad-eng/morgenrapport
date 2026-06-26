"""Sender rapporten som epost.

To leveringsveier, valgt automatisk ut fra hvilke hemmeligheter som finnes:

  * Gmail SMTP  – brukes hvis GMAIL_USER og GMAIL_APP_PASSWORD er satt.
                  Sender fra din egen Gmail og når HVEM SOM HELST (ingen
                  domeneverifisering). App-passord lages på
                  https://myaccount.google.com/apppasswords
  * Resend      – fallback hvis Gmail ikke er konfigurert. Krever verifisert
                  avsenderdomene for å nå andre enn din egen Resend-adresse.

Mottakerne legges i konvolutten (BCC-effekt) slik at de ikke ser hverandre.
"""
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.utils import formataddr


def send_report(config, html, date_str):
    recipients = config.get("recipients") or []
    if not recipients:
        raise RuntimeError(
            "Ingen mottakere. Sett GitHub-hemmeligheten RECIPIENTS (komma-skilt) "
            "eller fyll inn 'recipients' i config.yaml for lokal bruk."
        )
    subject = config.get("email_subject", "Morgenrapport {date}").format(date=date_str)

    gmail_user = (os.environ.get("GMAIL_USER") or "").strip()
    gmail_pw = (os.environ.get("GMAIL_APP_PASSWORD") or "").strip()
    if gmail_user and gmail_pw:
        _send_gmail(gmail_user, gmail_pw, recipients, subject, html)
    else:
        _send_resend(config, recipients, subject, html)


def _send_gmail(user, app_password, recipients, subject, html):
    """Sender via Googles SMTP-server. Når enhver mottaker, ingen domenekrav."""
    # App-passord vises ofte med mellomrom («abcd efgh ijkl mnop») – fjern dem.
    app_password = app_password.replace(" ", "")
    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = formataddr(("Morgenrapport", user))
    msg["To"] = user  # mottakerne skjules i konvolutten (under), ikke i headeren
    msg.attach(MIMEText(html, "html", "utf-8"))
    envelope_to = [user] + list(recipients)
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=30) as s:
        s.starttls()
        s.login(user, app_password)
        s.sendmail(user, envelope_to, msg.as_string())


def _send_resend(config, recipients, subject, html):
    import resend  # lat import: --no-email krever ikke epost-biblioteket
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError(
            "Verken Gmail (GMAIL_USER/GMAIL_APP_PASSWORD) eller RESEND_API_KEY "
            "er satt. Sett én av delene som miljøvariabel/GitHub-secret."
        )
    resend.api_key = api_key
    resend.Emails.send({
        "from": config["email_from"],
        "to": config["email_from"],  # avsender ser sin egen adresse i to-feltet
        "bcc": recipients,
        "subject": subject,
        "html": html,
    })
