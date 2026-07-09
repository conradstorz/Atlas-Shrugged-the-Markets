from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from atlas.db.database import normalize_asset_type, parse_money

CASH_ROW_LABEL = "Cash & Cash Investments"
_SKIP_SYMBOLS = {"Positions Total"}


def _column(header: dict[str, int], *candidates: str) -> int | None:
    """Return the index of the first header cell containing any candidate text."""
    for candidate in candidates:
        for name, idx in header.items():
            if candidate.lower() in name.lower():
                return idx
    return None


def load_schwab_positions(conn: sqlite3.Connection, portfolio_name: str, path: Path) -> int:
    """Load a Schwab "Positions" CSV export into ``portfolio_position``.

    Skips the preamble, blank lines, and the "Positions Total" row. Columns are
    located by name from the header row (the row whose first cell is "Symbol"),
    so column reordering is tolerated. The "Cash & Cash Investments" row is
    stored under the synthetic symbol ``CASH``. Existing positions for the
    portfolio are replaced.
    """
    conn.execute(
        "INSERT INTO portfolio (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
        (portfolio_name,),
    )
    portfolio_id = conn.execute(
        "SELECT id FROM portfolio WHERE name = ?", (portfolio_name,)
    ).fetchone()["id"]
    conn.execute("DELETE FROM portfolio_position WHERE portfolio_id = ?", (portfolio_id,))

    count = 0
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

            conn.execute(
                """
                INSERT INTO portfolio_position (
                    portfolio_id, symbol, description, asset_type, market_value
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(portfolio_id, symbol) DO UPDATE SET
                    description=excluded.description,
                    asset_type=excluded.asset_type,
                    market_value=excluded.market_value
                """,
                (portfolio_id, symbol, description, asset_type, market_value),
            )
            count += 1
    conn.commit()
    return count
