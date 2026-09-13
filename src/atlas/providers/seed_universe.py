from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping

from atlas.providers.base import ResearchDataProvider


def _split_seed_holdings(raw: str | None) -> list[str]:
    """Parse the uploaded select-list top-ten format, e.g. |NVDA||AAPL|."""
    if not raw or raw.strip() in {"--", ""}:
        return []
    return [item.strip().upper() for item in raw.split("|") if item.strip()]


class SeedUniverseProvider(ResearchDataProvider):
    """Parses the uploaded ETF Select List CSV that seeds the ``fund`` table.

    Each row carries fund metadata plus a pipe-delimited top-ten holdings
    cell (e.g. ``|NVDA||AAPL|``); this provider parses that cell into a list
    of symbols so the loader can persist both without re-parsing.

    It is a pure parser: it does not import ``sqlite3`` or ``atlas.db``, and
    it does not write anything. Persistence, including the precedence rule
    that skips holdings parsing for funds with real imported holdings, lives
    in ``atlas.db.database.load_seed_universe``.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def iter_funds(self) -> Iterable[Mapping[str, object]]:
        """Yield one mapping per seed CSV row with a non-blank ``Symbol``.

        Keys match the ``fund`` table column names (``symbol``,
        ``description``, ``fund_type``, ``category``, ``select_list``,
        ``gross_expense_ratio``, ``information_technology_exposure``,
        ``source``) so the loader can bind them straight into its upsert, plus
        two that are not ``fund`` columns: ``top_ten_holdings``, the raw cell
        text, and ``holding_symbols``, the symbols parsed out of it — which is
        what the loader inserts into ``fund_holding``. The raw cell is still
        yielded because it is the provider's unparsed input, not because
        anything stores it.
        """
        with self.path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                symbol = (row.get("Symbol") or "").strip().upper()
                if not symbol:
                    continue
                top_ten = row.get("Top Ten Holdings", "")
                yield {
                    "symbol": symbol,
                    "description": row.get("Description", ""),
                    "fund_type": row.get("Fund Type", ""),
                    "category": row.get("ETF Select List® Category", ""),
                    "select_list": row.get("ETF Select List", ""),
                    "top_ten_holdings": top_ten,
                    "gross_expense_ratio": row.get("Gross Expense Ratio", ""),
                    "information_technology_exposure": row.get(
                        "Sector Exposure: Information Technology", ""
                    ),
                    "source": row.get("Source", "Uploaded ETF Select List"),
                    "holding_symbols": _split_seed_holdings(top_ten),
                }
