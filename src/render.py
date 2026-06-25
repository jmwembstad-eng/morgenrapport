"""Bygger en ferdig formatert visningsmodell og renderer HTML via Jinja2-malen.
Samme HTML brukes både som epost-innhold og som nettside."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from jinja2 import Environment, FileSystemLoader

from . import fmt

ROOT = Path(__file__).resolve().parent.parent
OSLO = ZoneInfo("Europe/Oslo")

WEEKDAYS = ["mandag", "tirsdag", "onsdag", "torsdag", "fredag", "lørdag", "søndag"]
MONTHS = ["januar", "februar", "mars", "april", "mai", "juni",
          "juli", "august", "september", "oktober", "november", "desember"]


def _date_str(dt):
    return f"{WEEKDAYS[dt.weekday()]} {dt.day}. {MONTHS[dt.month - 1]} {dt.year}"


def build_context(report, config, now=None):
    now = now or datetime.now(OSLO)

    indices = []
    for r in report["indices"]:
        color, arrow = fmt.direction(r.get("change_pct"))
        indices.append({
            "name": r["name"],
            "region": r.get("region", ""),
            "close": fmt.nb_number(r.get("close")),
            "change": fmt.signed(r.get("change")),
            "change_pct": fmt.signed(r.get("change_pct"), suffix=" %"),
            "date": r.get("date") or fmt.DASH,
            "color": color,
            "arrow": arrow,
        })

    bonds = []
    for r in report["bonds"]:
        color, arrow = fmt.direction(r.get("change_bps"))
        y = r.get("yield_pct")
        bonds.append({
            "name": r["name"],
            "yield_pct": (fmt.nb_number(y) + " %") if y is not None else fmt.DASH,
            "change_bps": fmt.signed(r.get("change_bps"), 0, " bps"),
            "date": r.get("date") or fmt.DASH,
            "color": color,
            "arrow": arrow,
        })

    b = report["brent"]
    bcolor, barrow = fmt.direction(b.get("change_pct"))
    brent = {
        "price": fmt.nb_number(b.get("price")),
        "change": fmt.signed(b.get("change")),
        "change_pct": fmt.signed(b.get("change_pct"), suffix=" %"),
        "date": b.get("date") or fmt.DASH,
        "color": bcolor,
        "arrow": barrow,
    }

    # ── Strømpris ──────────────────────────────────────────────
    no_areas = ["NO1", "NO2", "NO3", "NO4", "NO5"]
    se_areas = ["SE1", "SE2", "SE3", "SE4"]
    power_map = {p["area"]: p for p in report.get("power", [])}

    def _pw(area):
        p = power_map.get(area, {})
        price = p.get("price")
        return {
            "area": area,
            "label": p.get("label", area),
            "price": fmt.nb_number(price) if price is not None else fmt.DASH,
            "date": p.get("date") or fmt.DASH,
        }

    power_no = [_pw(a) for a in no_areas if a in power_map]
    power_se = [_pw(a) for a in se_areas if a in power_map]
    power_de = _pw("DE-LU") if "DE-LU" in power_map else None

    # ── Makro ──────────────────────────────────────────────────
    def _macro_val(entry, key):
        d = entry.get(key, {})
        v, per = d.get("value"), d.get("period") or ""
        return fmt.nb_number(v) if v is not None else fmt.DASH, per

    macro = []
    for m in report.get("macro", []):
        cpi_v, cpi_p = _macro_val(m, "cpi")
        une_v, une_p = _macro_val(m, "unemployment")
        gdp_v, gdp_p = _macro_val(m, "gdp")
        macro.append({
            "name": m["name"],
            "cpi": cpi_v, "cpi_period": cpi_p,
            "unemployment": une_v, "unemployment_period": une_p,
            "gdp": gdp_v, "gdp_period": gdp_p,
        })

    # ── BESS-nyheter ───────────────────────────────────────────
    bess_news = report.get("bess_news", [])

    site_url = (config.get("site_url") or "").rstrip("/")
    report_url = f"{site_url}/reports/{now:%Y-%m-%d}.html" if site_url else ""

    return {
        "date_str": _date_str(now),
        "updated_str": now.strftime("%d.%m.%Y %H:%M"),
        "indices": indices,
        "bonds": bonds,
        "brent": brent,
        "power_no": power_no,
        "power_se": power_se,
        "power_de": power_de,
        "macro": macro,
        "bess_news": bess_news,
        "site_url": site_url,
        "report_url": report_url,
    }


def render_html(context):
    env = Environment(
        loader=FileSystemLoader(str(ROOT / "templates")),
        autoescape=True,  # alltid på – .j2-suffikset ville ellers deaktivert det
    )
    return env.get_template("report.html.j2").render(**context)
