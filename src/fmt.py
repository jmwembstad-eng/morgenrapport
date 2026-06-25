"""Tallformatering med norsk konvensjon (mellomrom som tusenskille, komma som desimal)
og farge-/pillogikk for endringer."""

GREEN = "#1a7f37"
RED = "#cf222e"
GREY = "#57606a"
DASH = "–"   # –
MINUS = "−"  # −


def nb_number(value, decimals=2):
    """5234.5 -> '5 234,50'. None -> '–'."""
    if value is None:
        return DASH
    s = f"{value:,.{decimals}f}"            # 5,234.50 (engelsk)
    return s.replace(",", " ").replace(".", ",")  # 5 234,50 (norsk)


def signed(value, decimals=2, suffix=""):
    """Endring med fortegn: '+1,23 %' / '−1,23 %'. None -> '–'."""
    if value is None:
        return DASH
    if value == 0:
        return f"0{(',' + '0' * decimals) if decimals else ''}{suffix}"
    sign = "+" if value > 0 else MINUS
    return f"{sign}{nb_number(abs(value), decimals)}{suffix}"


def direction(value):
    """Returnerer (farge, pil) basert på fortegn."""
    if value is None or value == 0:
        return (GREY, DASH)
    if value > 0:
        return (GREEN, "▲")  # ▲
    return (RED, "▼")        # ▼
