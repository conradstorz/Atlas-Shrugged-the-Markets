from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class OverlapResult:
    left_symbol: str
    right_symbol: str
    shared_count: int
    left_count: int
    right_count: int
    jaccard_percent: float
    shared_symbols: list[str]


def _holdings(conn: sqlite3.Connection, symbol: str) -> set[str]:
    rows = conn.execute(
        "SELECT holding_symbol FROM etf_holding WHERE etf_symbol = ? ORDER BY rank",
        (symbol.upper(),),
    ).fetchall()
    return {row["holding_symbol"] for row in rows}


def compare_etfs(conn: sqlite3.Connection, left_symbol: str, right_symbol: str) -> OverlapResult:
    """Compare parsed top-ten holdings for two ETFs.

    This v0.3 overlap is intentionally limited to the holdings present in the seed file.
    Full holdings support will replace this later.
    """
    left = _holdings(conn, left_symbol)
    right = _holdings(conn, right_symbol)
    shared = sorted(left & right)
    union_count = len(left | right)
    jaccard = (len(shared) / union_count * 100.0) if union_count else 0.0
    return OverlapResult(
        left_symbol=left_symbol.upper(),
        right_symbol=right_symbol.upper(),
        shared_count=len(shared),
        left_count=len(left),
        right_count=len(right),
        jaccard_percent=round(jaccard, 1),
        shared_symbols=shared,
    )


def top_repeated_holdings(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    """Return companies that appear most often in ETF top-ten holdings."""
    return conn.execute(
        """
        SELECT holding_symbol, COUNT(*) AS etf_count, GROUP_CONCAT(etf_symbol, ', ') AS etfs
        FROM etf_holding
        GROUP BY holding_symbol
        HAVING COUNT(*) > 1
        ORDER BY etf_count DESC, holding_symbol
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
