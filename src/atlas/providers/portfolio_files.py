from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable, Mapping

from atlas.parsing import normalize_asset_type, parse_money
from atlas.providers.base import PortfolioImportProvider

CASH_ROW_LABEL = "Cash & Cash Investments"
_SKIP_SYMBOLS = {"Positions Total"}


def _column(header: dict[str, int], *candidates: str) -> int | None:
    """Return the index of the first header cell containing any candidate text."""
    for candidate in candidates:
        for name, idx in header.items():
            if candidate.lower() in name.lower():
                return idx
    return None


class SchwabPositionsProvider(PortfolioImportProvider):
    """Parses a Schwab "Positions" CSV export.

    Skips the preamble, blank lines, and the "Positions Total" row. Columns
    are located by name from the header row (the row whose first cell is
    "Symbol"), so column reordering is tolerated. The "Cash & Cash
    Investments" row is yielded under the synthetic symbol ``CASH``.

    A symbol that appears in more than one account section of the file is
    yielded once per section, unsummed: multi-account accumulation is
    persistence behaviour that belongs to the loader
    (``atlas.portfolio.schwab.load_schwab_positions``), not to parsing.

    It is a pure parser: it does not import ``sqlite3`` or ``atlas.db``, and
    it does not write anything.
    """

    def import_file(self, path: Path) -> Iterable[Mapping[str, object]]:
        """Yield one mapping per parsed position row, in file order.

        Keys match the ``portfolio_position`` table columns used by the
        Schwab loader: ``symbol``, ``description``, ``asset_type``,
        ``market_value``.
        """
        header: dict[str, int] | None = None
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            for cells in csv.reader(csv_file):
                if not cells or not cells[0].strip():
                    continue
                first = cells[0].strip()

                if first == "Symbol":
                    header = {name.strip(): idx for idx, name in enumerate(cells)}
                    continue
                if header is None:
                    continue  # preamble before the first header
                if first in _SKIP_SYMBOLS or first.startswith("Positions for account"):
                    continue

                symbol = "CASH" if first == CASH_ROW_LABEL else first.upper()

                desc_idx = _column(header, "Description")
                value_idx = _column(header, "Market Value", "Mkt Val")
                asset_idx = _column(header, "Asset Type")

                description = cells[desc_idx].strip() if desc_idx is not None else ""
                market_value = parse_money(cells[value_idx] if value_idx is not None else None)
                asset_type = normalize_asset_type(cells[asset_idx] if asset_idx is not None else None)

                yield {
                    "symbol": symbol,
                    "description": description,
                    "asset_type": asset_type,
                    "market_value": market_value,
                }


class PortfolioCsvProvider(PortfolioImportProvider):
    """Parses a generic private portfolio CSV with Symbol and Market Value columns.

    Accepted symbol column names: Symbol, Ticker. Accepted market-value
    column names: Market Value, Value, Amount.

    It is a pure parser: it does not import ``sqlite3`` or ``atlas.db``, and
    it does not write anything.
    """

    def import_file(self, path: Path) -> Iterable[Mapping[str, object]]:
        """Yield one mapping per parsed row with a non-blank symbol.

        Keys match the ``portfolio_position`` table columns used by the
        generic loader: ``symbol``, ``description``, ``asset_type``,
        ``market_value``, ``notes``.
        """
        with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            reader = csv.DictReader(csv_file)
            for row in reader:
                symbol = (row.get("Symbol") or row.get("Ticker") or "").strip().upper()
                if not symbol:
                    continue
                raw_value = row.get("Market Value") or row.get("Value") or row.get("Amount") or "0"
                yield {
                    "symbol": symbol,
                    "description": row.get("Description", ""),
                    "asset_type": normalize_asset_type(row.get("Asset Type", "ETF")),
                    "market_value": parse_money(raw_value),
                    "notes": row.get("Notes", ""),
                }
