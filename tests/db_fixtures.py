"""Insert universe fixtures through one seam so schema changes touch one file.

These write whatever tables the current schema uses. Tests express *what*
exists (a fund, a holding, a score), not which tables store it.
"""
from __future__ import annotations

import sqlite3


def add_fund(
    conn: sqlite3.Connection,
    symbol: str,
    description: str = "",
    *,
    fund_type: str | None = None,
    category: str | None = None,
    select_list: str | None = None,
    gross_expense_ratio: str | None = None,
    information_technology_exposure: str | None = None,
    source: str | None = None,  # None matches what the raw fixture INSERTs left in the column
) -> None:
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'fund') "
        "ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, asset_type='fund'",
        (symbol, description),
    )
    # Mirror load_seed_universe's promotion: a symbol already registered as a
    # company stub (from being named as some fund's holding) must lose its
    # company row when it turns out to be a fund. Without this, add_fund could
    # build a symbol with BOTH a company row and a fund row at once -- a state
    # no production import path can reach (load_seed_universe promotes;
    # load_fund_holdings refuses to import holdings for a company-typed symbol).
    conn.execute("DELETE FROM company WHERE symbol = ?", (symbol,))
    conn.execute(
        """
        INSERT INTO fund (
            symbol, description, fund_type, category, select_list,
            gross_expense_ratio, information_technology_exposure, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            description=excluded.description,
            fund_type=excluded.fund_type,
            category=excluded.category,
            select_list=excluded.select_list,
            gross_expense_ratio=excluded.gross_expense_ratio,
            information_technology_exposure=excluded.information_technology_exposure,
            source=excluded.source
        """,
        (symbol, description, fund_type, category, select_list,
         gross_expense_ratio, information_technology_exposure, source),
    )


def add_holding(
    conn: sqlite3.Connection,
    fund_symbol: str,
    holding_symbol: str,
    *,
    holding_name: str | None = None,
    rank: int = 1,
    weight: float | None = None,
    source: str = "seed_top_ten",
) -> None:
    # Satisfy both FKs: the fund must exist, and the held symbol must be an
    # asset (company stub unless already registered).
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, '', 'fund') "
        "ON CONFLICT(symbol) DO NOTHING",
        (fund_symbol,),
    )
    conn.execute(
        "INSERT INTO fund (symbol, description) VALUES (?, '') "
        "ON CONFLICT(symbol) DO NOTHING",
        (fund_symbol,),
    )
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'company') "
        "ON CONFLICT(symbol) DO NOTHING",
        (holding_symbol, holding_name),
    )
    conn.execute(
        "INSERT OR IGNORE INTO company (symbol) "
        "SELECT symbol FROM asset WHERE symbol = ? AND asset_type = 'company'",
        (holding_symbol,),
    )
    conn.execute(
        """
        INSERT INTO fund_holding (
            fund_symbol, holding_symbol, holding_name, rank, weight, source
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (fund_symbol, holding_symbol, holding_name, rank, weight, source),
    )


def add_score(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    role: str = "Satellite",
    overall_score: int | None = None,
    ai_score: int = 4,
    resilience_score: int | None = None,
    cost_score: int | None = None,
    diversification_score: int | None = None,
    explanation: str = "test",
) -> None:
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, '', 'fund') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )
    conn.execute(
        "INSERT INTO fund (symbol, description) VALUES (?, '') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )
    conn.execute(
        """
        INSERT INTO fund_score (
            symbol, role, overall_score, ai_score, resilience_score,
            cost_score, diversification_score, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (symbol, role, overall_score, ai_score, resilience_score,
         cost_score, diversification_score, explanation),
    )
