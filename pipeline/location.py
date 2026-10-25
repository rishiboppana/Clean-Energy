"""Find the user's hub in free text with plain code (no LLM). Aliases live in data/hubs.json."""
import json
import re
from pathlib import Path

_HUBS = json.loads((Path(__file__).parent.parent / "data" / "hubs.json").read_text())["hubs"]
_PATTERNS = {h["id"]: [re.compile(r"\b" + re.escape(a) + r"\b") for a in h["aliases"]] for h in _HUBS}
HUB_NAMES = {h["id"]: h["name"] for h in _HUBS}


def detect_hub(text):
    """Hub id if the text names exactly one hub, else None (no match, or ambiguous like 'Dallas or Phoenix')."""
    low = text.lower()
    hits = [hid for hid, pats in _PATTERNS.items() if any(p.search(low) for p in pats)]
    return hits[0] if len(hits) == 1 else None


_ALIASES = sorted((a for h in _HUBS for a in h["aliases"]), key=len, reverse=True)  # longest first: "central iowa" before "iowa"
_STRIP = re.compile(
    r"(?:\b(?:i['’]?m|i am|we['’]?re|we are)\s+)?(?:\b(?:based\s+in|located\s+in|in|near|at|from|around)\s+)?(?:the\s+)?\b(?:"
    + "|".join(re.escape(a) for a in _ALIASES) + r")\b(?:\s+(?:city|area|metro))?", re.I)


def strip_location(text):
    """Remove the location phrase so the LLM only sees the job (it sometimes drops the job when a place is mentioned)."""
    return re.sub(r"\s+", " ", _STRIP.sub(" ", text)).strip(" ,.;:-")
