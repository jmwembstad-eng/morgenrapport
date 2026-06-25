"""Leser konfigurasjon fra config.yaml i prosjektroten."""
import os
import re
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parent.parent


# recipients er bevisst IKKE påkrevd her: i skyen kommer mottakerne fra
# GitHub-hemmeligheten RECIPIENTS, slik at private e-postadresser holdes
# utenfor det offentlige repoet.
_REQUIRED = ["email_from", "indices", "bonds"]


def load_config():
    with open(ROOT / "config.yaml", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)

    # Mottakere: miljøvariabelen RECIPIENTS (komma-, semikolon- eller linjeskilt)
    # overstyrer fila. Dette lar oss legge adressene i en GitHub-hemmelighet.
    env_rcpt = os.environ.get("RECIPIENTS", "").strip()
    if env_rcpt:
        cfg["recipients"] = [r.strip() for r in re.split(r"[,;\n]+", env_rcpt) if r.strip()]
    cfg.setdefault("recipients", [])

    missing = [k for k in _REQUIRED if not cfg.get(k)]
    if missing:
        raise ValueError(
            f"config.yaml mangler påkrevde felt: {', '.join(missing)}. "
            "Sjekk at alle felt er fylt ut."
        )
    return cfg
