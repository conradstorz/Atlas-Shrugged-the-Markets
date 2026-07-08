from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioSummary:
    name: str
    position_count: int
    total_value: float
    etf_value: float
    cash_or_unknown_value: float


def summarize_portfolio(conn: sqlite3.Connection, portfolio_name: str) -> PortfolioSummary:
    portfolio = conn.execute("SELECT id, name FROM portfolio WHERE name = ?", (portfolio_name,)).fetchone()
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_name}")
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS position_count,
            COALESCE(SUM(market_value), 0) AS total_value,
            COALESCE(SUM(CASE WHEN asset_type = 'ETF' THEN market_value ELSE 0 END), 0) AS etf_value,
            COALESCE(SUM(CASE WHEN asset_type <> 'ETF' THEN market_value ELSE 0 END), 0) AS cash_or_unknown_value
        FROM portfolio_position
        WHERE portfolio_id = ?
        """,
        (portfolio["id"],),
    ).fetchone()
    return PortfolioSummary(
        name=portfolio["name"],
        position_count=int(row["position_count"]),
        total_value=float(row["total_value"]),
        etf_value=float(row["etf_value"]),
        cash_or_unknown_value=float(row["cash_or_unknown_value"]),
    )


def portfolio_hidden_concentration(conn: sqlite3.Connection, portfolio_name: str, limit: int = 25) -> list[sqlite3.Row]:
    """Estimate hidden concentration using parsed ETF top-ten holdings.

    Because v0.3 seed holdings do not include holding weights, each top-ten holding is
    treated as equal inside that ETF's top-ten list. This is not final portfolio math;
    it is the first private-server proof of concept for hidden overlap.
    """
    portfolio = conn.execute("SELECT id FROM portfolio WHERE name = ?", (portfolio_name,)).fetchone()
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_name}")
    return conn.execute(
        """
        WITH position_total AS (
            SELECT SUM(market_value) AS total_value
            FROM portfolio_position
            WHERE portfolio_id = :portfolio_id
        ),
        top_ten_counts AS (
            SELECT etf_symbol, COUNT(*) AS holding_count
            FROM etf_holding
            GROUP BY etf_symbol
        )
        SELECT
            h.holding_symbol,
            COUNT(DISTINCT p.symbol) AS appears_in_positions,
            ROUND(SUM((p.market_value / position_total.total_value) / top_ten_counts.holding_count) * 100, 2) AS estimated_portfolio_percent,
            GROUP_CONCAT(DISTINCT p.symbol) AS source_etfs
        FROM portfolio_position p
        JOIN position_total
        JOIN etf_holding h ON h.etf_symbol = p.symbol
        JOIN top_ten_counts ON top_ten_counts.etf_symbol = p.symbol
        WHERE p.portfolio_id = :portfolio_id
          AND position_total.total_value > 0
        GROUP BY h.holding_symbol
        ORDER BY estimated_portfolio_percent DESC, holding_symbol
        LIMIT :limit
        """,
        {"portfolio_id": portfolio["id"], "limit": limit},
    ).fetchall()
