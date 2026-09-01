from __future__ import annotations

import csv
from pathlib import Path
from typing import Iterable

from atlas.exceptions import AtlasDataError
from atlas.parsing import parse_percent
from atlas.providers.base import FundHolding, FundHoldingsProvider

# Order matters: more specific candidates are checked first so, e.g.,
# Vanguard's "Holdings" name column does not win the symbol slot over its
# "Ticker" column, and Invesco's "Holding Ticker" symbol column does not win
# the name slot over its "Name" column.
_SYMBOL_CANDIDATES = ("ticker", "symbol", "holding")
_NAME_CANDIDATES = ("name", "description", "holdings", "security")
_WEIGHT_CANDIDATES = (
    "weight",
    "% of net assets",
    "% of assets",
    "% of funds",
    "portfolio weight",
    "allocation",
)


def _column(header: dict[str, int], *candidates: str) -> int | None:
    """Return the index of the first header cell containing any candidate text."""
    for candidate in candidates:
        for name, idx in header.items():
            if candidate.lower() in name.lower():
                return idx
    return None


class HoldingsFileProvider(FundHoldingsProvider):
    """Parses an issuer-published fund holdings CSV (with weights).

    Issuer files open with preamble lines (fund name, as-of date,
    disclaimers) before the real header. The header is located as the first
    row that contains both a symbol-like and a weight-like column; once
    found, its columns are located by name so issuer-specific column order
    and extra columns are tolerated. This mirrors
    ``atlas.portfolio.schwab.load_schwab_positions`` and its ``_column``
    helper, but for a different issuer-file shape.

    It is a pure parser: it does not import ``sqlite3`` or ``atlas.db``, and
    it does not write anything. Persistence lives in
    ``atlas.db.database.load_fund_holdings``.
    """

    def __init__(self, path: Path) -> None:
        self.path = path

    def iter_holdings(self) -> Iterable[FundHolding]:
        """Return the fund's holdings as a list of :class:`FundHolding`.

        Rows are materialized (not streamed) because the fractions-vs-percent
        guard below needs the total of every parsed weight before any holding
        can be considered safe to use.
        """
        header: dict[str, int] | None = None
        symbol_idx = name_idx = weight_idx = None

        # symbol -> [holding_name, weight_total], plus first-seen order.
        accumulated: dict[str, list[object]] = {}
        order: list[str] = []
        parsed_row_count = 0

        with self.path.open("r", encoding="utf-8-sig", newline="") as csv_file:
            for cells in csv.reader(csv_file):
                if not cells or not any(cell.strip() for cell in cells):
                    continue  # blank row

                if header is None:
                    candidate_header = {cell.strip(): idx for idx, cell in enumerate(cells)}
                    candidate_symbol_idx = _column(candidate_header, *_SYMBOL_CANDIDATES)
                    candidate_weight_idx = _column(candidate_header, *_WEIGHT_CANDIDATES)
                    if candidate_symbol_idx is not None and candidate_weight_idx is not None:
                        header = candidate_header
                        symbol_idx = candidate_symbol_idx
                        weight_idx = candidate_weight_idx
                        name_idx = _column(header, *_NAME_CANDIDATES)
                    continue  # preamble row, or the header row itself

                first = cells[0].strip()
                if first.lower().startswith("total"):
                    continue

                symbol_raw = cells[symbol_idx].strip() if symbol_idx < len(cells) else ""
                if symbol_raw == "" or symbol_raw == "--" or symbol_raw.upper() == "N/A":
                    # Cash / futures / FX sleeve: deliberately excluded so its
                    # share of the fund stays unmodeled rather than being
                    # misattributed to an equity.
                    continue

                weight_raw = cells[weight_idx] if weight_idx < len(cells) else None
                weight = parse_percent(weight_raw)
                if weight is None:
                    continue

                symbol = symbol_raw.upper()
                name: str | None = None
                if name_idx is not None and name_idx < len(cells):
                    name_raw = cells[name_idx].strip()
                    name = name_raw or None

                parsed_row_count += 1
                if symbol in accumulated:
                    accumulated[symbol][1] = accumulated[symbol][1] + weight
                else:
                    accumulated[symbol] = [name, weight]
                    order.append(symbol)

        holdings = [
            FundHolding(
                holding_symbol=symbol,
                holding_name=accumulated[symbol][0],  # type: ignore[arg-type]
                weight=accumulated[symbol][1],  # type: ignore[arg-type]
            )
            for symbol in order
        ]
        total = sum(h.weight for h in holdings)

        if parsed_row_count > 5 and total <= 1.5:
            raise AtlasDataError(
                f"{self.path}: holdings weights sum to {total:.4f}, which looks like fractions "
                "(e.g. 0.0683) rather than percent. Convert weights to percent (e.g. 6.83) before "
                "importing."
            )
        if total > 100.5:
            raise AtlasDataError(
                f"{self.path}: holdings weights sum to {total:.2f}%, which exceeds 100%. The file "
                "may be malformed, or the wrong column may have been matched as the weight column."
            )

        return holdings
