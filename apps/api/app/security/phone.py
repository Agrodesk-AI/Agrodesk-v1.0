import re

_DIGITS = re.compile(r"\D+")


def normalize_phone(raw: str, default_region: str = "IN") -> str:
    """Return E.164-like string. MVP implementation; swap for the `phonenumbers` lib later."""
    if not raw:
        raise ValueError("phone required")
    cleaned = _DIGITS.sub("", raw)
    if raw.strip().startswith("+") and 10 <= len(cleaned) <= 15:
        return "+" + cleaned
    if default_region == "IN":
        if len(cleaned) == 10:
            return "+91" + cleaned
        if len(cleaned) == 12 and cleaned.startswith("91"):
            return "+" + cleaned
        if len(cleaned) == 11 and cleaned.startswith("0"):
            return "+91" + cleaned[1:]
    raise ValueError(f"cannot normalize phone: {raw!r}")
