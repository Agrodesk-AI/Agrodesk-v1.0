"""Two-layer moderation (design §3.8).

Layer 1 (code, ~ms, always on): phone numbers, links/payment handles, scam
phrases, blocklisted words. Layer 2 (classifier adapter, swappable; Fake in
dev) runs only on content that passed layer 1. Low confidence or classifier
failure never auto-blocks; it queues for a human.

Verdicts:
    approve -> publish
    flag    -> publish=false, status in_review, queue for a human
    block   -> reject at submit with a reason the poster can fix
"""

import re
import unicodedata
from dataclasses import dataclass, field
from typing import Protocol

# Contact stays masked until both sides agree (rentals) / dealers via routing.
# Matches Indian mobiles in any script's digits once normalised, with spaces,
# dashes or a +91/0 prefix.
_PHONE = re.compile(r"(?:\+?91|0)?[\s\-.]*[6-9](?:[\s\-.]*\d){9}(?!\d)")
_LINK = re.compile(r"https?://|www\.|\b[a-z0-9-]+\.(?:com|in|net|org|xyz|io|me|ly)\b", re.I)
_UPI = re.compile(
    r"\b[\w.\-]{2,}@(?:ybl|okaxis|okhdfcbank|oksbi|okicici|paytm|upi|apl|ibl|axl)\b", re.I
)

# Cheap known-bad phrases (scams). Extend from moderation reviews; keep lowercase.
SCAM_PHRASES: frozenset[str] = frozenset(
    {
        "lottery",
        "you have won",
        "advance payment",
        "send otp",
        "share otp",
        "kyc update",
        "loan without documents",
        "guaranteed subsidy",
        "लॉटरी",
        "इनाम जीता",
        "ओटीपी भेजें",
        "एडवांस पेमेंट",
        "लॉटरी लागली",
        "ओटीपी पाठवा",
        "बक्षीस जिंकले",
    }
)
# Abuse / slur blocklist. Kept out of the repo on purpose: loaded at deploy time
# (e.g. from a secrets-managed file) via `load_blocklist`. Empty in dev/tests
# unless a test sets it.
BLOCKLIST: set[str] = set()


def load_blocklist(words: list[str]) -> None:
    BLOCKLIST.clear()
    BLOCKLIST.update(w.strip().lower() for w in words if w.strip())


def normalize_digits(text: str) -> str:
    """Devanagari / Gujarati / Tamil / … digits -> ASCII so the phone regex sees them."""
    out = []
    for ch in text:
        if ch.isdigit() and not ch.isascii():
            try:
                out.append(str(unicodedata.digit(ch)))
                continue
            except ValueError:
                pass
        out.append(ch)
    return "".join(out)


@dataclass
class Verdict:
    action: str  # approve | flag | block
    reasons: list[str] = field(default_factory=list)
    layer: str = "prescreen"
    confidence: float | None = None

    def as_dict(self) -> dict:
        return {
            "action": self.action,
            "reasons": self.reasons,
            "layer": self.layer,
            "confidence": self.confidence,
        }


def prescreen(text: str) -> Verdict:
    norm = normalize_digits(text)
    low = norm.lower()
    if _PHONE.search(norm):
        return Verdict("block", ["phone_number"])
    if any(w in low for w in BLOCKLIST):
        return Verdict("block", ["blocked_word"])
    reasons = []
    if _LINK.search(norm):
        reasons.append("link")
    if _UPI.search(norm):
        reasons.append("payment_handle")
    if any(p in low for p in SCAM_PHRASES):
        reasons.append("scam_phrase")
    return Verdict("flag", reasons) if reasons else Verdict("approve")


class ContentClassifier(Protocol):
    async def classify(self, text: str, *, kind: str, language: str) -> Verdict: ...


class FakeClassifier:
    """Dev/test stand-in for the LLM classifier: approves with full confidence."""

    async def classify(self, text: str, *, kind: str, language: str) -> Verdict:
        return Verdict("approve", [], layer="classifier", confidence=1.0)


MIN_CONFIDENCE = 0.7
_classifier: ContentClassifier = FakeClassifier()


def set_classifier(c: ContentClassifier) -> None:
    global _classifier
    _classifier = c


async def moderate(text: str, *, kind: str, language: str) -> Verdict:
    v = prescreen(text)
    if v.action != "approve":
        return v
    try:
        c = await _classifier.classify(text, kind=kind, language=language)
    except Exception:  # provider down: code layer is the floor; a human looks later
        return Verdict("flag", ["classifier_unavailable"], layer="classifier")
    if c.action == "block" and (c.confidence or 0) < MIN_CONFIDENCE:
        return Verdict(
            "flag", c.reasons + ["low_confidence"], layer="classifier", confidence=c.confidence
        )
    if c.action == "approve" and (c.confidence or 0) < MIN_CONFIDENCE:
        return Verdict(
            "flag", c.reasons + ["low_confidence"], layer="classifier", confidence=c.confidence
        )
    return c
