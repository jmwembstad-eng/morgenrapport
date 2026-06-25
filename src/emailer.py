"""Sender rapporten som epost via Resend (https://resend.com)."""
import os


def send_report(config, html, date_str):
    import resend  # lat import: generering/--no-email krever ikke epost-biblioteket
    api_key = os.environ.get("RESEND_API_KEY")
    if not api_key:
        raise RuntimeError(
            "RESEND_API_KEY mangler. Sett den som miljøvariabel lokalt, "
            "eller som GitHub-secret når den kjører i skyen."
        )
    resend.api_key = api_key
    recipients = config.get("recipients") or []
    if not recipients:
        raise RuntimeError(
            "Ingen mottakere. Sett GitHub-hemmeligheten RECIPIENTS (komma-skilt) "
            "eller fyll inn 'recipients' i config.yaml for lokal bruk."
        )
    subject = config.get("email_subject", "Morgenrapport {date}").format(date=date_str)
    resend.Emails.send({
        "from": config["email_from"],
        "to": config["email_from"],  # avsender ser sin egen adresse i to-feltet
        "bcc": recipients,
        "subject": subject,
        "html": html,
    })
