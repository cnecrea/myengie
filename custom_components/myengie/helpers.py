"""Funcții și constante utilitare pentru integrarea MyENGIE România (Engie Romania)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.util import dt as dt_util

from .const import DOMAIN


# ══════════════════════════════════════════════
# Mapping-uri luni
# ══════════════════════════════════════════════

MONTHS_EN_RO: dict[str, str] = {
    "January": "ianuarie",
    "February": "februarie",
    "March": "martie",
    "April": "aprilie",
    "May": "mai",
    "June": "iunie",
    "July": "iulie",
    "August": "august",
    "September": "septembrie",
    "October": "octombrie",
    "November": "noiembrie",
    "December": "decembrie",
}

MONTHS_NUM_RO: dict[int, str] = {
    1: "ianuarie",
    2: "februarie",
    3: "martie",
    4: "aprilie",
    5: "mai",
    6: "iunie",
    7: "iulie",
    8: "august",
    9: "septembrie",
    10: "octombrie",
    11: "noiembrie",
    12: "decembrie",
}

# Mapping-uri tip citire (Engie)
READING_TYPE_MAP: dict[str, str] = {
    "01": "Citire distribuitor",
    "02": "Autocitire",
    "03": "Estimare",
}

# ══════════════════════════════════════════════
# Mapping-uri utilități și unități de măsură
# ══════════════════════════════════════════════

DIVISION_LABEL: dict[str, str] = {
    "gaz": "Gaz",
    "elec": "Energie Electrică",
}

DIVISION_SHORT: dict[str, str] = {
    "gaz": "gaz",
    "elec": "electricitate",
}

UNIT_NORMALIZE: dict[str, str] = {
    "MC": "m³",
    "M3": "m³",
    "m3": "m³",
    "KWH": "kWh",
    "kwh": "kWh",
    "MWH": "MWh",
    "mwh": "MWh",
}

# Mapping luni Engie prognosis (cheile sunt "01"-"12")
PROGNOSIS_MONTH_MAP: dict[str, str] = {
    "01": "ianuarie",
    "02": "februarie",
    "03": "martie",
    "04": "aprilie",
    "05": "mai",
    "06": "iunie",
    "07": "iulie",
    "08": "august",
    "09": "septembrie",
    "10": "octombrie",
    "11": "noiembrie",
    "12": "decembrie",
}

# ══════════════════════════════════════════════
# Mapping-uri traducere atribute factură/balanță
# ══════════════════════════════════════════════

INVOICE_KEY_MAP: dict[str, str] = {
    "invoice_number": "Număr factură",
    "invoice_date": "Data facturii",
    "due_date": "Data scadenței",
    "amount": "Valoare",
    "paid_amount": "Sumă achitată",
    "balance": "Sold",
    "status": "Stare",
    "currency": "Monedă",
    "period": "Perioadă",
}

INVOICE_MONEY_KEYS: set[str] = {
    "amount",
    "paid_amount",
    "balance",
    "total",
}


# ══════════════════════════════════════════════
# Funcții de formatare
# ══════════════════════════════════════════════

def format_ron(value: float) -> str:
    """Formatează o valoare numerică în format românesc (1.234,56)."""
    formatted = f"{value:,.2f}"
    return formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def format_number_ro(value: float | int | str) -> str:
    """Formatează un număr cu separatorul zecimal românesc (virgulă).

    Exemple:
        4.029   → '4,029'
        124.91  → '124,91'
        11.9    → '11,9'
        0.424   → '0,424'
        100     → '100'
        100.0   → '100'
    """
    try:
        num = float(value)
    except (ValueError, TypeError):
        return str(value)
    if num == int(num):
        return str(int(num))
    text = str(num)
    return text.replace(".", ",")


def format_invoice_due_message(
    display_value: float, raw_date: str, date_format: str = "%d.%m.%Y"
) -> str:
    """Formatează mesajul de scadență pentru o factură.

    Returnează un mesaj de tip:
    - „Restanță de X lei, termen depășit cu N zile"
    - „De achitat astăzi: X lei"
    - „Sumă de X lei scadentă pe luna LUNA (N zile)"
    """
    parsed_date = datetime.strptime(raw_date, date_format)
    month_name_en = parsed_date.strftime("%B")
    month_name_ro = MONTHS_EN_RO.get(month_name_en, "necunoscut")
    days_until_due = (parsed_date.date() - dt_util.now().date()).days

    if days_until_due < 0:
        day_unit = "zi" if abs(days_until_due) == 1 else "zile"
        return (
            f"Restanță de {format_ron(display_value)} lei, "
            f"termen depășit cu {abs(days_until_due)} {day_unit}"
        )
    if days_until_due == 0:
        return (
            f"De achitat astăzi, {dt_util.now().strftime('%d.%m.%Y')}: "
            f"{format_ron(display_value)} lei"
        )
    day_unit = "zi" if days_until_due == 1 else "zile"
    return (
        f"Sumă de {format_ron(display_value)} lei scadentă pe luna "
        f"{month_name_ro} ({days_until_due} {day_unit})"
    )


# ══════════════════════════════════════════════
# Funcții utilitare
# ══════════════════════════════════════════════

def mask_email(email: str) -> str:
    """Mascarea adresei de email: a*****b@gmail.com."""
    if not email or "@" not in email:
        return email or "—"
    local, domain = email.rsplit("@", 1)
    if len(local) <= 1:
        masked = local
    elif len(local) == 2:
        masked = f"{local[0]}*"
    else:
        masked = f"{local[0]}{'*' * (len(local) - 2)}{local[-1]}"
    return f"{masked}@{domain}"


def normalize_unit(unit: str) -> str:
    """Normalizează unitățile de măsură."""
    return UNIT_NORMALIZE.get(unit, unit)


def build_address_string(address: dict) -> str:
    """Construiește o adresă citibilă din obiectul adresă Engie.

    Formatul Engie: {"street": "...", "number": "...", "city": "...", "county": "..."}
    """
    if not isinstance(address, dict):
        return ""

    parts = []
    street = address.get("street", "")
    number = address.get("number", "")
    if street:
        if number:
            parts.append(f"{street} {number}")
        else:
            parts.append(street)

    block = address.get("block", "")
    staircase = address.get("staircase", "")
    apartment = address.get("apartment", "")

    detail_parts = []
    if block:
        detail_parts.append(f"bl. {block}")
    if staircase:
        detail_parts.append(f"sc. {staircase}")
    if apartment:
        detail_parts.append(f"ap. {apartment}")
    if detail_parts:
        parts.append(", ".join(detail_parts))

    city = address.get("city", "")
    county = address.get("county", "")
    if city:
        if county:
            parts.append(f"{city}, {county}")
        else:
            parts.append(city)
    elif county:
        parts.append(county)

    postal = address.get("postal_code", "")
    if postal:
        parts.append(postal)

    return ", ".join(parts)
