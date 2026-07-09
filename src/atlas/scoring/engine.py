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


def _universe_holding_frequency(conn: sqlite3.Connection) -> dict[str, int]:
    """Map each holding to the number of ETFs whose top-ten contains it."""
    rows = conn.execute(
        """
        SELECT holding_symbol, COUNT(DISTINCT etf_symbol) AS df
        FROM etf_holding
        GROUP BY holding_symbol
        """
    ).fetchall()
    return {row["holding_symbol"]: row["df"] for row in rows}


def measured_diversification(holdings: list[str], freq: dict[str, int]) -> int | None:
    """Score 0-10 for how much unique exposure an ETF's holdings add.

    A holding held by only this ETF (document frequency <= 1) is "unique"; one
    also held by other ETFs is "crowded". The score is the fraction of unique
    holdings, so an ETF that just piles into the same widely-held names scores
    low. Returns ``None`` when there are no parsed holdings to measure.
    """
    if not holdings:
        return None
    unique = sum(1 for holding in holdings if freq.get(holding, 0) <= 1)
    return round(unique / len(holdings) * 10)


def score_etf(row: sqlite3.Row, diversification_override: int | None = None) -> ScoreBreakdown:
    """Generate a transparent, partly data-grounded score for an ETF.

    Cost comes from the real expense ratio, resilience is eroded by the real
    information-technology exposure, and diversification is measured from actual
    top-ten holdings overlap (passed in via ``diversification_override``). The AI
    signal is still a keyword heuristic; valuation and drawdown data are not yet
    connected. Kept deliberately explainable rather than final.
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

    # AI signal is nudged up by real information-technology concentration.
    if tech is not None:
        if tech >= 40:
            ai_score = max(ai_score, 8)
        elif tech >= 20:
            ai_score = max(ai_score, 7)

    # Resilience erodes with real IT concentration: every 10 percentage points
    # of technology exposure above 20% costs one point of resilience.
    if tech is not None and tech > 20:
        resilience_score = max(1, resilience_score - round((tech - 20) / 10))

    # Diversification is the MEASURED uniqueness of this ETF's holdings versus
    # the rest of the universe. When we have no parsed holdings to measure
    # (e.g. bond funds), keep the role-based default.
    if diversification_override is not None:
        diversification_score = diversification_override

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

    diversification_basis = (
        "measured from top-ten holdings overlap"
        if diversification_override is not None
        else "role-based default (no parsed holdings)"
    )
    explanation = (
        f"Role={role}; AI={ai_score}/10; resilience={resilience_score}/10; "
        f"diversification={diversification_score}/10 ({diversification_basis}); "
        f"cost={cost_score}/10. Cost uses the real expense ratio and resilience "
        "reflects real information-technology concentration; AI remains heuristic "
        "and valuation/drawdown data are not yet connected."
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


def read_scores(conn: sqlite3.Connection) -> list[ScoreBreakdown]:
    """Return previously persisted ETF scores without recomputing them.

    Reads the ``etf_score`` table (populated by :func:`score_all`) so read-only
    callers such as the web dashboard don't have to re-score and re-write on
    every request.
    """
    rows = conn.execute(
        """
        SELECT symbol, role, overall_score, ai_score, resilience_score,
               cost_score, diversification_score, explanation
        FROM etf_score
        ORDER BY overall_score DESC, symbol
        """
    ).fetchall()
    return [
        ScoreBreakdown(
            symbol=row["symbol"],
            role=row["role"],
            overall_score=row["overall_score"],
            ai_score=row["ai_score"],
            resilience_score=row["resilience_score"],
            cost_score=row["cost_score"],
            diversification_score=row["diversification_score"],
            explanation=row["explanation"],
        )
        for row in rows
    ]


def score_all(conn: sqlite3.Connection) -> list[ScoreBreakdown]:
    freq = _universe_holding_frequency(conn)
    rows = conn.execute("SELECT * FROM etf ORDER BY symbol").fetchall()
    scores = []
    for row in rows:
        holdings = [
            holding["holding_symbol"]
            for holding in conn.execute(
                "SELECT holding_symbol FROM etf_holding WHERE etf_symbol = ? ORDER BY rank",
                (row["symbol"],),
            ).fetchall()
        ]
        override = measured_diversification(holdings, freq)
        scores.append(score_etf(row, diversification_override=override))
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
