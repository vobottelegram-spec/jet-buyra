
from __future__ import annotations

import json
import re
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Optional

SOURCE_NAME = "NerkhAra"
SOURCE_URL = "https://nerkhara.com/api/v1/latest/usd.json"
REQUEST_TIMEOUT = 8
MAX_INPUT_LENGTH = 128
MAX_AMOUNT = Decimal("1000000000000")
USD_QUANTUM = Decimal("0.000001")

class CurrencyError(ValueError):
    pass

@dataclass(frozen=True)
class ExchangeRate:
    toman_per_usd: Decimal
    updated_utc: datetime
    source_name: str = SOURCE_NAME
    source_url: str = SOURCE_URL

    @property
    def stale(self) -> bool:
        return datetime.now(timezone.utc) - self.updated_utc > timedelta(hours=1)

    @property
    def expires_utc(self) -> datetime:
        return self.updated_utc + timedelta(hours=1)

def _digits(s: str) -> str:
    table = str.maketrans("۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩", "01234567890123456789")
    return s.translate(table).replace("٬", ",").replace("٫", ".")

_SUFFIXES = (("ریال", "IRR"), ("ريال", "IRR"), ("تومان", "IRT"),
             ("دلار", "USD"), ("IRR", "IRR"), ("IRT", "IRT"),
             ("USD", "USD"), ("$", "USD"))

def parse_amount(text: str) -> Optional[tuple[str, Decimal]]:
    
    if not isinstance(text, str) or len(text) > MAX_INPUT_LENGTH:
        return None
    s = _digits(text).strip()
    if not s:
        return None
    currency = None
    for suffix, code in _SUFFIXES:
        if s.lower().endswith(suffix.lower()):
            currency, s = code, s[:-len(suffix)].strip()
            break
    s = s.replace(" ", "")
    if not re.fullmatch(r"(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", s):
        return None
    try:
        amount = Decimal(s.replace(",", ""))
    except InvalidOperation:
        return None
    if not amount.is_finite() or amount < 0 or amount > MAX_AMOUNT:
        return None
    if amount == 0:
        return (currency or "IRT", amount)
    if currency is None:
        return None
    if currency in ("IRR", "IRT") and amount != amount.to_integral_value():
        return None
    if currency == "USD" and max(0, -amount.as_tuple().exponent) > 6:
        return None
    return currency, amount

def fetch_rate() -> ExchangeRate:
    
    req = urllib.request.Request(SOURCE_URL, headers={"Accept": "application/json", "User-Agent": "AccountSellBot/1.0"})
    try:
        with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as response:
            data = json.loads(response.read().decode("utf-8"), parse_float=Decimal, parse_int=Decimal)
    except Exception as exc:
        raise CurrencyError(f"Unable to fetch exchange rate: {exc}") from exc
    if not isinstance(data, dict):
        raise CurrencyError("Malformed exchange-rate response")
    item = data.get("item")
    if not isinstance(item, dict) or item.get("id") != "usd" or item.get("unit") != "IRT":
        raise CurrencyError("Unexpected exchange-rate item or unit")
    if item.get("stale") is not False:
        raise CurrencyError("Exchange-rate source is stale or freshness unknown")
    raw_rate = item.get("price")
    try:
        rate = raw_rate if isinstance(raw_rate, Decimal) else Decimal(str(raw_rate))
    except (InvalidOperation, TypeError, ValueError):
        raise CurrencyError("Malformed exchange rate")
    if not rate.is_finite() or rate <= 0:
        raise CurrencyError("Exchange rate must be positive and finite")
    stamp = item.get("updated_utc")
    if not isinstance(stamp, str):
        raise CurrencyError("Missing updated_utc timestamp")
    try:
        updated = datetime.fromisoformat(stamp.replace("Z", "+00:00"))
                                                                             
        if updated.tzinfo is None:
            updated = updated.replace(tzinfo=timezone.utc)
        updated = updated.astimezone(timezone.utc)
    except (ValueError, OverflowError) as exc:
        raise CurrencyError("Malformed updated_utc timestamp") from exc
    now = datetime.now(timezone.utc)
    if updated > now + timedelta(minutes=5):
        raise CurrencyError("Exchange-rate timestamp is in the future")
    if now - updated > timedelta(hours=1):
        raise CurrencyError("Exchange-rate data is stale")
    return ExchangeRate(rate, updated)

def convert(amount: Decimal, currency: str, rate: ExchangeRate) -> dict[str, Decimal]:
    
    amount = Decimal(amount)
    if not amount.is_finite() or amount < 0:
        raise CurrencyError("Amount must be finite and nonnegative")
    if currency == "USD":
        usd = amount
        irt = usd * rate.toman_per_usd
        irr = irt * 10
    elif currency == "IRT":
        irt = amount
        usd = irt / rate.toman_per_usd
        irr = irt * 10
    elif currency == "IRR":
        irr = amount
        irt = irr / 10
        usd = irt / rate.toman_per_usd
    else:
        raise CurrencyError("Currency must be USD, IRR, or IRT")
    return {"usd": usd, "irr": irr, "irt": irt}

def format_usd(amount: Decimal) -> str:
    return f"{Decimal(amount).quantize(USD_QUANTUM, rounding=ROUND_HALF_UP):.6f}"

def format_irr(amount: Decimal) -> str:
    return f"{Decimal(amount).quantize(Decimal('1'), rounding=ROUND_HALF_UP):,.0f}"

def format_irt(amount: Decimal) -> str:
    return f"{Decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):,.2f}"
