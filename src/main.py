"""Hovedflyt: hent data -> render HTML -> skriv nettside -> send epost.

Kjør lokalt:
    py -m src.main --no-email      # generer nettside uten å sende epost
    py -m src.main                 # generer + send epost (krever RESEND_API_KEY)

Tidssone-vakt: sender kun når klokken er `send_hour_oslo` i Europe/Oslo,
slik at de to UTC-cron-tidspunktene (vinter/sommer) ikke gir dobbel utsending.
Sett miljøvariabelen FORCE_SEND=1 for å overstyre (brukes ved manuell kjøring).
"""
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from . import config as cfg
from . import fetch_data, render, emailer

ROOT = Path(__file__).resolve().parent.parent
OSLO = ZoneInfo("Europe/Oslo")


def should_run(config, now):
    if os.environ.get("FORCE_SEND"):
        return True
    hour = config.get("send_hour_oslo")
    if hour is None:
        return True
    # Aksepterer send_hour og timen etter (absorberer GitHub Actions cron-forsinkelse).
    if not (int(hour) <= now.hour <= int(hour) + 1):
        return False
    # Idempotens: hopp over hvis dagens rapport allerede er skrevet.
    # Forhindrer dobbel utsending når primær- og reserve-cron begge lander i vinduet.
    if (ROOT / "docs" / "reports" / f"{now:%Y-%m-%d}.html").exists():
        print("Rapport allerede generert i dag, hopper over.")
        return False
    return True


def main():
    config = cfg.load_config()
    now = datetime.now(OSLO)

    if not should_run(config, now):
        print(f"Hopper over: klokken er {now:%H:%M} i Oslo "
              f"(sender kun kl. {config.get('send_hour_oslo')}).")
        return

    print("Henter markedsdata ...")
    report = fetch_data.fetch_all(config)

    context = render.build_context(report, config, now)
    html = render.render_html(context)

    docs = ROOT / "docs"
    (docs / "reports").mkdir(parents=True, exist_ok=True)
    (docs / "index.html").write_text(html, encoding="utf-8")
    (docs / "reports" / f"{now:%Y-%m-%d}.html").write_text(html, encoding="utf-8")
    print(f"Nettside skrevet til {docs / 'index.html'}")

    if "--no-email" in sys.argv:
        print("--no-email: hopper over epostutsending.")
        return

    emailer.send_report(config, html, context["date_str"])
    print(f"Epost sendt til: {', '.join(config['recipients'])}")


if __name__ == "__main__":
    main()
