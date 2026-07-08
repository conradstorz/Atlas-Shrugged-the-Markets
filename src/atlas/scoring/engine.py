from __future__ import annotations

import re
import sqlite3

from atlas.scoring.model import ScoreBreakdown

CORE_TERMS = ("broad market", "total", "s&p 500", "large blend")
DIVIDEND_TERMS = ("dividend", "income")
VALUE_TERMS = ("value", "fundamental")
BOND_TERMS = ("bond", "treasury", "municipal", "fixed income")
SECTOR_TERMS = ("technology", "semiconductor", "energy", "health care", "financial", "utilities")


def _parse_percent(value: str | None) -> float | None:
    if not value or value.strip() in {"--", ""}:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", value)
    return float(match.group()) if match else None


def score_etf(row: sqlite3.Row) -> ScoreBreakdown:
    """Generate the first transparent heuristic score for an ETF.

    This v0.2 scorer is deliberately simple. It exists to make the workflow real,
    not to pretend we have completed the final investment model.
    """
    symbol = row["symbol"]
    text = f"{row['description']} {row['category']}".lower()
    expense = _parse_percent(row["gross_expense_ratio"])
    tech = _parse_percent(row["information_technology_exposure"])

    role = "Satellite"
    ai_score = 4
    resilience_score = 5
    diversification_score = 5

    if any(term in text for term in BOND_TERMS):
        role = "Defensive"
        ai_score = 1
        resilience_score = 9
        diversification_score = 7
    elif any(term in text for term in DIVIDEND_TERMS):
        role = "Quality Income"
        ai_score = 5
        resilience_score = 8
        diversification_score = 7
    elif any(term in text for term in VALUE_TERMS):
        role = "Value / Fundamental"
        ai_score = 6
        resilience_score = 8
        diversification_score = 7
    elif any(term in text for term in CORE_TERMS):
        role = "Foundation"
        ai_score = 8
        resilience_score = 7
        diversification_score = 9
    elif any(term in text for term in SECTOR_TERMS):
        role = "Thematic Satellite"
        ai_score = 8 if "technology" in text or "semiconductor" in text else 5
        resilience_score = 3 if ai_score >= 8 else 5
        diversification_score = 3

    if tech is not None:
        if tech >= 40:
            ai_score = max(ai_score, 8)
            resilience_score = min(resilience_score, 4)
            diversification_score = min(diversification_score, 4)
        elif tech >= 20:
            ai_score = max(ai_score, 7)

    if expense is None:
        cost_score = 6
    elif expense <= 0.05:
        cost_score = 10
    elif expense <= 0.15:
        cost_score = 9
    elif expense <= 0.35:
        cost_score = 7
    elif expense <= 0.60:
        cost_score = 5
    else:
        cost_score = 3

    overall = round(
        ai_score * 2.0
        + resilience_score * 2.0
        + diversification_score * 2.0
        + cost_score * 2.0
        + 20
    )
    overall = max(0, min(100, overall))

    explanation = (
        f"Role={role}; AI={ai_score}/10; resilience={resilience_score}/10; "
        f"diversification={diversification_score}/10; cost={cost_score}/10. "
        "This is a v0.2 heuristic score and should be refined with holdings, "
        "overlap, valuation, and historical drawdown data."
    )
    return ScoreBreakdown(
        symbol=symbol,
        role=role,
        overall_score=overall,
        ai_score=ai_score,
        resilience_score=resilience_score,
        cost_score=cost_score,
        diversification_score=diversification_score,
        explanation=explanation,
    )


def score_all(conn: sqlite3.Connection) -> list[ScoreBreakdown]:
    rows = conn.execute("SELECT * FROM etf ORDER BY symbol").fetchall()
    scores = [score_etf(row) for row in rows]
    for score in scores:
        conn.execute(
            """
            INSERT INTO etf_score (
                symbol, role, overall_score, ai_score, resilience_score,
                cost_score, diversification_score, explanation
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                role=excluded.role,
                overall_score=excluded.overall_score,
                ai_score=excluded.ai_score,
                resilience_score=excluded.resilience_score,
                cost_score=excluded.cost_score,
                diversification_score=excluded.diversification_score,
                explanation=excluded.explanation
            """,
            (
                score.symbol,
                score.role,
                score.overall_score,
                score.ai_score,
                score.resilience_score,
                score.cost_score,
                score.diversification_score,
                score.explanation,
            ),
        )
    conn.commit()
    return sorted(scores, key=lambda item: item.overall_score, reverse=True)
