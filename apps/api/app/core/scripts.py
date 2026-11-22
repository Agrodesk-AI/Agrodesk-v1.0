"""Which script each supported language is written in, and script detection.

Used so a name stored without a known language (LGD "Name (In Local)" columns
mix scripts across states) is still shown to readers of a language written in
that script, and never to readers of a different script.
"""

LANG_SCRIPT: dict[str, str] = {
    "hi": "deva",
    "mr": "deva",
    "gu": "gujr",
    "pa": "guru",
    "bn": "beng",
    "as": "beng",
    "or": "orya",
    "ta": "taml",
    "te": "telu",
    "kn": "knda",
    "ml": "mlym",
    "ur": "arab",
}

_RANGES: tuple[tuple[int, int, str], ...] = (
    (0x0900, 0x097F, "deva"),
    (0x0980, 0x09FF, "beng"),
    (0x0A00, 0x0A7F, "guru"),
    (0x0A80, 0x0AFF, "gujr"),
    (0x0B00, 0x0B7F, "orya"),
    (0x0B80, 0x0BFF, "taml"),
    (0x0C00, 0x0C7F, "telu"),
    (0x0C80, 0x0CFF, "knda"),
    (0x0D00, 0x0D7F, "mlym"),
    (0x0600, 0x06FF, "arab"),
)


def detect_script(s: str) -> str | None:
    for ch in s:
        cp = ord(ch)
        for lo, hi, script in _RANGES:
            if lo <= cp <= hi:
                return script
    return None


def unique_lang_for_script(script: str | None) -> str | None:
    """The language for a script when only one supported language uses it."""
    langs = [lang for lang, sc in LANG_SCRIPT.items() if sc == script]
    return langs[0] if len(langs) == 1 else None
