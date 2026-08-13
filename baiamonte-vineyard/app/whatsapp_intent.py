"""Small, deterministic WhatsApp intent guards used before AI replies."""

from __future__ import annotations

import re
from typing import Any


def is_submission(body: str, analysis: dict[str, Any]) -> bool:
    """Return true only for deliberate operational record submissions."""
    text = " ".join(str(body or "").strip().split())
    if not text or analysis.get("contains_question") or "?" in text:
        return False
    if re.match(
        r"^(?:what|when|where|why|who|how|is|are|can|could|would|will|show|tell|give|check|weather|forecast|status|"
        r"cosa|quando|dove|perch[eé]|chi|come|[eè]|sono|puoi|potresti|mostra|dimmi|meteo|previsioni|stato)\b",
        text,
        re.I,
    ):
        return False
    explicit_report = re.search(
        r"\b(?:record|log|report|add|save|worked|completed|finished|applied|treated|harvested|picked|received|observed|"
        r"registra|annota|segnala|aggiungi|salva|lavorat[oaie]|completat[oaie]|finit[oaie]|applicat[oaie]|trattat[oaie]|"
        r"raccolt[oaie]|ricevut[oaie]|osservat[oaie])\b",
        text,
        re.I,
    )
    measured_report = re.search(
        r"\b\d+(?:[.,]\d+)?\s*(?:h|hr|hrs|hours?|ore|min|kg|g|l|ml|mm|cm|m|%|°c|c|crates?|cassette?)\b",
        text,
        re.I,
    )
    classification = str(analysis.get("classification") or "other")
    return classification != "other" and bool(explicit_report or measured_report)
