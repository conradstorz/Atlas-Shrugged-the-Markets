from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas.providers.portfolio_files import SchwabPositionsProvider


def load_schwab_positions(conn: sqlite3.Connection, portfolio_name: str, path: Path) -> int:
    """Load a Schwab "Positions" CSV export into ``portfolio_position``.

    Skips the preamble, blank lines, and the "Positions Total" row. Columns are
    located by name from the header row (the row whose first cell is "Symbol"),
    so column reordering is tolerated. The "Cash & Cash Investments" row is
    stored under the synthetic symbol ``CASH``. Existing positions for the
    portfolio are replaced on each load. A symbol that appears in more than
    one account section of the file has its market value summed across those
    sections. Returns the number of distinct stored positions.
    """
    conn.execute(
        "INSERT INTO portfolio (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
        (portfolio_name,),
    )
    portfolio_id = conn.execute(
        "SELECT id FROM portfolio WHERE name = ?", (portfolio_name,)
    ).fetchone()["id"]
    conn.execute("DELETE FROM portfolio_position WHERE portfolio_id = ?", (portfolio_id,))

    for position in SchwabPositionsProvider().import_file(path):
        conn.execute(
            """
            INSERT INTO portfolio_position (
                portfolio_id, symbol, description, asset_type, market_value
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(portfolio_id, symbol) DO UPDATE SET
                description=excluded.description,
                asset_type=excluded.asset_type,
                market_value=portfolio_position.market_value + excluded.market_value
            """,
            (
                portfolio_id,
                position["symbol"],
                position["description"],
                position["asset_type"],
                position["market_value"],
            ),
        )
    conn.commit()
    return conn.execute(
        "SELECT COUNT(*) AS count FROM portfolio_position WHERE portfolio_id = ?",
        (portfolio_id,),
    ).fetchone()["count"]
