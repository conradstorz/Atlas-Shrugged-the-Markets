from __future__ import annotations

import re


def parse_money(raw: str | None) -> float:
    """Parse a Schwab-style money cell (``$9,846.00``) into a float.

    Placeholders (``--``, ``N/A``), empty strings, and ``None`` become ``0.0``.
    Never raises on malformed input.
    """
    if raw is None:
        return 0.0
    text = str(raw).strip()
    if text in {"", "--", "N/A"}:
        return 0.0
    text = text.replace("$", "").replace(",", "").strip()
    try:
        return float(text or 0)
    except ValueError:
        return 0.0


def normalize_asset_type(raw: str | None) -> str:
    """Normalize a security-type label to the Atlas vocabulary.

    Returns one of: ``equity``, ``etf``, ``mutual_fund``, ``cash``, ``other``.
    Matching is case-insensitive and substring-based so it tolerates both the
    Schwab labels ("ETFs & Closed End Funds") and legacy CSV values ("ETF").
    """
    text = (raw or "").strip().lower()
    if not text or text in {"--", "n/a"}:
        return "other"
    if "cash" in text or "money market" in text:
        return "cash"
    if "mutual fund" in text:
        return "mutual_fund"
    if "etf" in text or "closed end" in text:
        return "etf"
    if "equity" in text:
        return "equity"
    return "other"


def parse_percent(value: str | None) -> float | None:
    """Parse a percent-style cell (``6.83%`` or ``6.83``) into a float.

    Returns ``None`` for placeholders (``--``, empty, ``None``) or when no
    number is found. Extracts the first signed decimal number it finds, so
    both ``"6.83%"`` and ``"6.83"`` parse to ``6.83``.
    """
    if not value or value.strip() in {"--", ""}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group()) if match else None
