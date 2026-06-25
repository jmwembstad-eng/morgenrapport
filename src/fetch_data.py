"""Henter all markedsdata til rapporten.

Hver kilde hentes isolert i en try/except: hvis én kilde svikter en morgen,
blir verdien None (vises som «–» i rapporten) og resten sendes som normalt.

Viktige fallgruver som er håndtert per kilde:
  * Rad-rekkefølge: US Treasury er NYEST først; Norges Bank, ECB og BoE er
    ELDST først (siste rad = nyeste). Riksbanken (JSON) er eldst først.
  * Enheter: alle renter er i prosent. Endring regnes om til basispunkter (bps).
  * Datoformat varierer (MM/DD/YYYY, DD Mon YYYY, YYYY-MM-DD) – normaliseres til ISO.

Alle kildene er gratis og krever ingen API-nøkkel.
"""
import csv
import io
import json
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import requests

OSLO = ZoneInfo("Europe/Oslo")
TIMEOUT = 25
HEADERS = {"User-Agent": "Morgenrapport/1.0"}

_EN_MONTHS = {m: i for i, m in enumerate(
    ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
     "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"], start=1)}


# ──────────────────────────── HTTP ────────────────────────────
def _get_text(url):
    r = requests.get(url, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    return r.text


# ─────────────────────── yfinance (indekser + Brent) ──────────
def _yf_last_two(ticker, _retries=2):
    """Returnerer (siste_close, forrige_close, iso_dato) for en yfinance-ticker.

    Yahoo Finance kan av og til returnere tomme svar (rate-limiting / midlertidig feil).
    Vi prøver opptil _retries ganger med 4 sekunders pause mellom forsøkene.
    """
    import time
    import yfinance as yf  # lat import: indeks/Brent degraderer pent hvis biblioteket feiler
    closes = None
    for attempt in range(_retries + 1):
        hist = yf.Ticker(ticker).history(period="1mo", interval="1d", auto_adjust=False)
        closes = hist["Close"].dropna()
        if len(closes) >= 2:
            break
        if attempt < _retries:
            time.sleep(4)
    if closes is None or len(closes) == 0:
        raise ValueError(f"ingen data for {ticker} etter {_retries + 1} forsøk")
    last = float(closes.iloc[-1])
    prev = float(closes.iloc[-2]) if len(closes) >= 2 else None
    iso = closes.index[-1].date().isoformat()
    return last, prev, iso


def _index(cfg):
    name, ticker, region = cfg["name"], cfg["ticker"], cfg.get("region", "")
    try:
        last, prev, iso = _yf_last_two(ticker)
        change = (last - prev) if prev is not None else None
        pct = (change / prev * 100) if (change is not None and prev) else None
        return {"name": name, "region": region, "close": last,
                "change": change, "change_pct": pct, "date": iso}
    except Exception as e:
        print(f"  ! Indeks {name} ({ticker}) feilet: {e}")
        return {"name": name, "region": region, "close": None,
                "change": None, "change_pct": None, "date": None}


def _brent(ticker):
    try:
        last, prev, iso = _yf_last_two(ticker)
        change = (last - prev) if prev is not None else None
        pct = (change / prev * 100) if (change is not None and prev) else None
        return {"price": last, "change": change, "change_pct": pct, "date": iso}
    except Exception as e:
        print(f"  ! Brent ({ticker}) feilet: {e}")
        return {"price": None, "change": None, "change_pct": None, "date": None}


# ─────────────────────── 10-årige statsrenter ─────────────────
def _bond_us():
    """US Treasury par yield curve – CSV, NYEST først, kolonne '10 Yr'."""
    year = datetime.now(OSLO).year
    base = ("https://home.treasury.gov/resource-center/data-chart-center/"
            "interest-rates/daily-treasury-rates.csv/{y}/all"
            "?type=daily_treasury_yield_curve&field_tdr_date_value={y}&page&_format=csv")

    def rows_for(y):
        text = _get_text(base.format(y=y))
        rows = list(csv.reader(io.StringIO(text)))
        return rows[0], rows[1:]

    header, data = rows_for(year)
    if len(data) < 2:                      # tidlig i januar: hent også fjoråret
        _, prev_year = rows_for(year - 1)
        data = data + prev_year
    idx = header.index("10 Yr")
    latest, prev = data[0], data[1]        # nyest først
    iso = datetime.strptime(latest[0], "%m/%d/%Y").date().isoformat()
    return float(latest[idx]), float(prev[idx]), iso


def _bond_no():
    """Norges Bank – semikolon-CSV, ELDST først."""
    url = ("https://data.norges-bank.no/api/data/GOVT_GENERIC_RATES/"
           "B.10Y.GBON.?format=csv&lastNObservations=2")
    rows = list(csv.reader(io.StringIO(_get_text(url)), delimiter=";"))
    header = rows[0]
    vi, ti = header.index("OBS_VALUE"), header.index("TIME_PERIOD")
    data = [r for r in rows[1:] if len(r) > vi and r[vi].strip()]
    latest, prev = data[-1], data[-2]      # eldst først → siste = nyeste
    return float(latest[vi]), float(prev[vi]), latest[ti]


def _bond_se():
    """Riksbanken Swea API – JSON, ELDST først."""
    today = datetime.now(OSLO).date()
    start = (today - timedelta(days=30)).isoformat()
    url = (f"https://api.riksbank.se/swea/v1/Observations/"
           f"SEGVB10YC/{start}/{today.isoformat()}")
    data = [d for d in json.loads(_get_text(url)) if d.get("value") is not None]
    latest, prev = data[-1], data[-2]
    return float(latest["value"]), float(prev["value"]), latest["date"]


def _bond_de():
    """ECB euro-områdets AAA-kurve 10Y (nær proxy for tysk Bund) – CSV, ELDST først."""
    url = ("https://data-api.ecb.europa.eu/service/data/YC/"
           "B.U2.EUR.4F.G_N_A.SV_C_YM.SR_10Y?lastNObservations=2&format=csvdata")
    rows = list(csv.reader(io.StringIO(_get_text(url))))
    header = rows[0]
    vi, ti = header.index("OBS_VALUE"), header.index("TIME_PERIOD")
    data = [r for r in rows[1:] if len(r) > vi and r[vi].strip()]
    latest, prev = data[-1], data[-2]
    return float(latest[vi]), float(prev[vi]), latest[ti]


def _bond_gb():
    """Bank of England – 10-årig gilt (IUDMNZC), CSV, ELDST først."""
    today = datetime.now(OSLO).date()
    frm = (today - timedelta(days=30)).strftime("%d/%b/%Y")
    to = today.strftime("%d/%b/%Y")
    url = ("https://www.bankofengland.co.uk/boeapps/database/_iadb-fromshowcolumns.asp"
           f"?csv.x=yes&Datefrom={frm}&Dateto={to}&SeriesCodes=IUDMNZC"
           "&CSVF=TN&UsingCodes=Y&VPD=Y&VFD=N")
    rows = list(csv.reader(io.StringIO(_get_text(url))))
    data = [r for r in rows[1:] if len(r) >= 2 and r[1].strip()]
    latest, prev = data[-1], data[-2]
    d, mon, y = latest[0].split()
    iso = date(int(y), _EN_MONTHS[mon], int(d)).isoformat()
    return float(latest[1]), float(prev[1]), iso


_BOND_FETCHERS = {
    "US": _bond_us, "NO": _bond_no, "SE": _bond_se,
    "DE": _bond_de, "GB": _bond_gb,
}


def _bonds(bond_cfgs):
    out = []
    for c in bond_cfgs:
        code, name = c["code"], c["name"]
        try:
            y, prev, iso = _BOND_FETCHERS[code]()
            change_bps = round((y - prev) * 100) if (y is not None and prev is not None) else None
            out.append({"code": code, "name": name, "yield_pct": y,
                        "change_bps": change_bps, "date": iso})
        except Exception as e:
            print(f"  ! Obligasjon {name} ({code}) feilet: {e}")
            out.append({"code": code, "name": name, "yield_pct": None,
                        "change_bps": None, "date": None})
    return out


# ─────────────────────── Strømpris ────────────────────────────
_POWER_LABELS = {
    "NO1": "NO1 – Øst",    "NO2": "NO2 – Sør",       "NO3": "NO3 – Midt",
    "NO4": "NO4 – Nord",   "NO5": "NO5 – Vest",
    "SE1": "SE1 – Luleå",  "SE2": "SE2 – Sundsvall",
    "SE3": "SE3 – Stockholm", "SE4": "SE4 – Malmö",
    "DE-LU": "DE/LU",
}

_NO_AREAS = {"NO1", "NO2", "NO3", "NO4", "NO5"}
_OTHER_AREAS = {"SE1", "SE2", "SE3", "SE4", "DE-LU"}


def _power_no(area, day):
    """hvakosterstrommen.no – daglig gjennomsnitt for norske soner (NOK/kWh og EUR/kWh)."""
    y, m, d = day.year, day.month, day.day
    url = f"https://www.hvakosterstrommen.no/api/v1/prices/{y}/{m:02d}-{d:02d}_{area}.json"
    hours = json.loads(_get_text(url))
    prices_eur = [float(h["EUR_per_kWh"]) * 1000 for h in hours if h.get("EUR_per_kWh") is not None]
    avg = sum(prices_eur) / len(prices_eur) if prices_eur else None
    return avg  # EUR/MWh


def _power_smard_de(day):
    """SMARD (Bundesnetzagentur) – dag-frem-spotpris for DE-LU (EUR/MWh), ingen nøkkel."""
    idx = json.loads(_get_text("https://www.smard.de/app/chart_data/4169/DE/index_hour.json"))
    ts = idx["timestamps"][-1]
    data = json.loads(_get_text(
        f"https://www.smard.de/app/chart_data/4169/DE/4169_DE_hour_{ts}.json"))
    from datetime import timezone
    prices = []
    for unix_ms, price in data["series"]:
        if price is not None:
            dt = datetime.fromtimestamp(unix_ms / 1000, tz=timezone.utc).date()
            if dt == day:
                prices.append(float(price))
    return sum(prices) / len(prices) if prices else None


def _power_energidata(areas, day):
    """Energi Data Service (DK) – dag-frem-priser for SE (EUR/MWh).
    Kan være rate-limited; feil degraderer pent til None."""
    import urllib.parse
    f = json.dumps({"PriceArea": list(areas)})
    ds = day.isoformat()
    de = (day + timedelta(days=1)).isoformat()
    url = (f"https://api.energidataservice.dk/dataset/Elspotprices"
           f"?start={ds}&end={de}&filter={urllib.parse.quote(f)}&sort=HourDK+asc")
    recs = json.loads(_get_text(url)).get("records", [])
    from collections import defaultdict
    area_hours = defaultdict(list)
    for rec in recs:
        v = rec.get("SpotPriceEUR")
        if v is not None:
            area_hours[rec["PriceArea"]].append(float(v))
    return {a: (sum(v) / len(v) if v else None) for a, v in area_hours.items()}


def _power(areas):
    """Henter strømpris for angitte prisområder. Returnerer liste med dicts."""
    today = datetime.now(OSLO).date()
    no_areas = [a for a in areas if a in _NO_AREAS]
    other = [a for a in areas if a in _OTHER_AREAS]
    prices = {}

    for a in no_areas:
        try:
            prices[a] = {"price": _power_no(a, today), "date": today.isoformat()}
        except Exception as e:
            print(f"  ! Strømpris {a} feilet: {e}")
            prices[a] = {"price": None, "date": None}

    # DE-LU: SMARD (ingen nøkkel, alltid tilgjengelig)
    if "DE-LU" in other:
        try:
            prices["DE-LU"] = {"price": _power_smard_de(today), "date": today.isoformat()}
        except Exception as e:
            print(f"  ! Strømpris DE-LU (SMARD) feilet: {e}")
            prices["DE-LU"] = {"price": None, "date": None}

    # SE1-SE4: Energi Data Service (kan være rate-limited)
    se_areas = [a for a in other if a.startswith("SE")]
    if se_areas:
        try:
            ed = _power_energidata(se_areas, today)
            for a in se_areas:
                prices[a] = {"price": ed.get(a), "date": today.isoformat()}
        except Exception as e:
            print(f"  ! Strømpris SE (Energi Data Service) feilet: {e}")
            for a in se_areas:
                prices[a] = {"price": None, "date": None}

    return [{"area": a, "label": _POWER_LABELS.get(a, a),
             "price": prices.get(a, {}).get("price"),
             "date": prices.get(a, {}).get("date"),
             "currency": "EUR/MWh"} for a in areas]


# ─────────────────────── Makroøkonomi ─────────────────────────
_MACRO_GEO = {"NO": "Norge", "SE": "Sverige", "DE": "Tyskland",
              "UK": "Storbritannia", "EA20": "Eurosonen"}
_EUROSTAT = "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
_SINCE = "2024-01"  # start for tidsserier (henter siste tilgjengelig)
# EA20 ikke i une_rt_m → bruker EU27_2020; UK ikke i Eurostat BNP/HICP etter Brexit
_UNE_EA_GEO = "EU27_2020"
_ONS_MONTHS = {"JAN": "01", "FEB": "02", "MAR": "03", "APR": "04",
               "MAY": "05", "JUN": "06", "JUL": "07", "AUG": "08",
               "SEP": "09", "OCT": "10", "NOV": "11", "DEC": "12"}


def _unemployment_uk():
    """ONS MGSX – UK arbeidsledighet (16+, sesongkorrigert, %)."""
    url = ("https://www.ons.gov.uk/employmentandlabourmarket/peoplenotinwork/"
           "unemployment/timeseries/mgsx/lms/data")
    months = json.loads(_get_text(url)).get("months", [])
    if not months:
        raise ValueError("ingen månedlige UK-arbeidsledighetstall fra ONS")
    last = months[-1]
    year, mon = last["date"].split()
    iso = f"{year}-{_ONS_MONTHS[mon]}"
    return {"value": float(last["value"]), "period": iso}


def _eurostat(dataset, geos, extra):
    """SDMX-JSON fra Eurostat. geos er liste; extra er dict med tilleggsfiltre."""
    params = [("format", "JSON"), ("sinceTimePeriod", _SINCE)] + \
             [("geo", g) for g in geos] + list(extra.items())
    r = requests.get(f"{_EUROSTAT}/{dataset}", params=params, headers=HEADERS, timeout=TIMEOUT)
    r.raise_for_status()
    data = r.json()
    geo_idx = data["dimension"]["geo"]["category"]["index"]    # {"DE": 0, "SE": 1, ...}
    time_cat = data["dimension"]["time"]["category"]
    time_idx = time_cat["index"]                               # {"2024-01": 0, ...}
    time_labels = time_cat.get("label", {v: k for k, v in time_idx.items()})
    n_time = data["size"][-1]
    values = data.get("value", {})
    out = {}
    for geo, gi in geo_idx.items():
        # Finn siste tilgjengelige verdi for dette landet (hopp over None)
        for ti in range(n_time - 1, -1, -1):
            flat = str(gi * n_time + ti)
            if flat in values:
                out[geo] = {"value": values[flat],
                            "period": time_labels.get(ti) or list(time_idx.keys())[ti]}
                break
        else:
            out[geo] = {"value": None, "period": None}
    return out



def _macro():
    """Henter KPI, arbeidsledighet og BNP-vekst fra Eurostat."""
    out = {g: {} for g in ["NO", "SE", "DE", "UK", "EA20"]}

    # KPI/inflasjon
    # prc_hicp_manr er avviklet (stopper 2025-12); bruker prc_hicp_minr med TOTAL+RCH_A
    # NO er tilgjengelig i Eurostat HICP; UK er ikke med etter Brexit
    try:
        hicp_geos = ["NO", "SE", "DE", "EA20"]
        eu_cpi = _eurostat("prc_hicp_minr", hicp_geos, {"coicop18": "TOTAL", "unit": "RCH_A"})
        for g in hicp_geos:
            out[g]["cpi"] = eu_cpi.get(g, {})
    except Exception as e:
        print(f"  ! Eurostat KPI feilet: {e}")

    # Arbeidsledighet: NO/SE/DE via Eurostat; UK via ONS (ikke i Eurostat etter Brexit)
    try:
        une = _eurostat("une_rt_m", ["NO", "SE", "DE", _UNE_EA_GEO],
                        {"sex": "T", "age": "TOTAL", "s_adj": "SA", "unit": "PC_ACT"})
        for g in ["NO", "SE", "DE"]:
            out[g]["unemployment"] = une.get(g, {})
        out["EA20"]["unemployment"] = une.get(_UNE_EA_GEO, {})
    except Exception as e:
        print(f"  ! Eurostat arbeidsledighet feilet: {e}")
    try:
        out["UK"]["unemployment"] = _unemployment_uk()
    except Exception as e:
        print(f"  ! ONS UK arbeidsledighet feilet: {e}")

    # BNP-vekst: NO/SE/DE/EA20 (UK ikke tilgjengelig i Eurostat etter Brexit)
    try:
        gdp = _eurostat("namq_10_gdp", ["NO", "SE", "DE", "EA20"],
                        {"na_item": "B1GQ", "unit": "CLV_PCH_PRE", "s_adj": "SCA"})
        for g in gdp:
            out[g]["gdp"] = gdp[g]
    except Exception as e:
        print(f"  ! Eurostat BNP feilet: {e}")

    return [{"geo": g, "name": _MACRO_GEO[g], **out[g]}
            for g in ["NO", "SE", "DE", "UK", "EA20"]]


# ─────────────────────── BESS-nyheter (Google News RSS) ───────
import xml.etree.ElementTree as ET
from email.utils import parsedate_to_datetime


def _bess_news(max_items=8):
    """Henter BESS-relaterte nyheter fra Google News RSS for Norden."""
    queries = [
        '"battery storage" Nordic',
        'BESS "battery energy storage" Scandinavia',
        "batterilager Norden energilager",
        "energilager batteri Sverige Denmark",
    ]
    seen, items = set(), []
    for q in queries:
        try:
            q_enc = q.replace(" ", "+")
            url = f"https://news.google.com/rss/search?q={q_enc}&hl=en&gl=US&ceid=US:en"
            root = ET.fromstring(_get_text(url))
            for item in root.findall(".//item"):
                title = item.findtext("title", "").strip()
                # Fjern «– Kilde» fra slutten av tittelen
                if " - " in title:
                    title = title.rsplit(" - ", 1)[0].strip()
                link = item.findtext("link", "").strip()
                pub_raw = item.findtext("pubDate", "")
                src_el = item.find("source")
                source = src_el.text.strip() if src_el is not None else ""
                try:
                    pub_dt = parsedate_to_datetime(pub_raw)
                    pub_iso = pub_dt.date().isoformat()
                except Exception:
                    pub_iso = ""
                key = title[:80]
                if key not in seen:
                    seen.add(key)
                    items.append({"title": title, "link": link,
                                  "source": source, "date": pub_iso})
        except Exception as e:
            print(f"  ! BESS-nyheter feilet for '{q[:30]}': {e}")

    items.sort(key=lambda x: x["date"], reverse=True)
    return items[:max_items]


# ──────────────────────────── samlet ──────────────────────────
def fetch_all(config):
    power_areas = [a["area"] for a in config.get("power_areas", [])]
    return {
        "indices": [_index(i) for i in config["indices"]],
        "bonds": _bonds(config["bonds"]),
        "brent": _brent(config.get("brent_ticker", "BZ=F")),
        "power": _power(power_areas) if power_areas else [],
        "macro": _macro(),
        "bess_news": _bess_news(config.get("bess_news_max_items", 8)),
    }
