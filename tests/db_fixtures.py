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
    source: str | None = "seed",
) -> None:
    conn.execute(
        """
        INSERT INTO etf (
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
    conn.execute(
        """
        INSERT INTO etf_holding (
            etf_symbol, holding_symbol, holding_name, rank, weight, source
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
        """
        INSERT INTO etf_score (
            symbol, role, overall_score, ai_score, resilience_score,
            cost_score, diversification_score, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (symbol, role, overall_score, ai_score, resilience_score,
         cost_score, diversification_score, explanation),
    )
