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
