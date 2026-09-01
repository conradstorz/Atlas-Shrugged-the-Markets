from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from math import log10

from atlas.analytics.overlap import holdings_weight_source
from atlas.parsing import parse_percent
from atlas.scoring.model import ScoreBreakdown

CORE_TERMS = ("broad market", "total", "s&p 500", "large blend")
DIVIDEND_TERMS = ("dividend", "income")
VALUE_TERMS = ("value", "fundamental")
BOND_TERMS = ("bond", "treasury", "municipal", "fixed income")
SECTOR_TERMS = ("technology", "semiconductor", "energy", "health care", "financial", "utilities")

# --- Diversification: breadth where it can be measured, nothing where it can't

# Breadth is read on a log scale. The gap between a 30-holding fund and a
# 300-holding fund matters far more to an investor than the gap between 2,500
# and 2,800 holdings, which a linear count would treat as equally important.
# BREADTH_FLOOR is a fund holding no more names than a top-ten list (0/10);
# BREADTH_CEILING is total-market breadth (10/10) — a US total-market index
# runs to roughly three thousand names.
BREADTH_FLOOR = 10
BREADTH_CEILING = 3000

# Breadth is only measurable from a holdings file that covers essentially the
# whole fund. An issuer's full holdings file sums to ~100% of net assets; a
# top-ten-only export sums to ~30-40%. This threshold separates "the whole
# fund" from "a partial export" using data already stored. A partial file means
# breadth is unknown, not small.
FULL_COVERAGE_THRESHOLD = 90.0

# Points of the 0-100 scale shared by the scored components; the remaining 20
# is the base every fund starts from. The budget is fixed, so a component that
# cannot be measured is dropped and the same points are spread over the
# components that remain — never substituted with a guess.
COMPONENT_BUDGET = 80.0
COMPONENT_MAX = 10


@dataclass(frozen=True)
class DiversificationMeasure:
    """A fund's measured breadth, together with the evidence behind it.

    ``holdings_count`` and ``weight_total`` travel with the score so the
    explanation can state its own basis rather than asserting a number the
    reader has to trust.
    """

    score: int
    holdings_count: int
    weight_total: float


def breadth_score(holdings_count: int) -> int:
    """Score 0-10 for how many names a fund actually holds, on a log scale.

    ``BREADTH_FLOOR`` holdings or fewer score 0, ``BREADTH_CEILING`` or more
    score 10, and the interval between them is logarithmic. A count of zero or
    less is not breadth at all and scores 0.
    """
    if holdings_count <= 0:
        return 0
    span = log10(BREADTH_CEILING) - log10(BREADTH_FLOOR)
    raw = (log10(holdings_count) - log10(BREADTH_FLOOR)) / span * COMPONENT_MAX
    return max(0, min(COMPONENT_MAX, round(raw)))


def measured_diversification(
    conn: sqlite3.Connection, etf_symbol: str
) -> DiversificationMeasure | None:
    """Measure a fund's diversification as the breadth of what it holds.

    Returns ``None`` — meaning "not measured", never a stand-in value — unless
    the fund's holdings come from an imported holdings file
    (``source='holdings_file'``) whose weights total at least
    :data:`FULL_COVERAGE_THRESHOLD` percent of the fund.

    Seed rows are top-ten *membership*, not a holdings list, and a partial
    issuer export is a slice of the fund. Counting either as breadth would
    report every seed fund — including a total-market index — as holding ten
    names, which is a worse lie than saying nothing.
    """
    symbol = etf_symbol.upper()
    if holdings_weight_source(conn, symbol) != "holdings_file":
        return None
    row = conn.execute(
        """
        SELECT COUNT(*) AS holdings_count, COALESCE(SUM(weight), 0.0) AS weight_total
        FROM etf_holding
        WHERE etf_symbol = ? AND source = 'holdings_file'
        """,
        (symbol,),
    ).fetchone()
    holdings_count = int(row["holdings_count"])
    weight_total = float(row["weight_total"])
    if holdings_count <= 0 or weight_total < FULL_COVERAGE_THRESHOLD:
        return None
    return DiversificationMeasure(
        score=breadth_score(holdings_count),
        holdings_count=holdings_count,
        weight_total=weight_total,
    )


def score_etf(
    row: sqlite3.Row,
    diversification: DiversificationMeasure | None = None,
) -> ScoreBreakdown:
    """Generate a transparent, partly data-grounded score for an ETF.

    Cost comes from the real expense ratio, resilience is eroded by the real
    information-technology exposure, and diversification is the measured
    breadth of the fund's imported holdings file (passed in via
    ``diversification``). The AI signal is still a keyword heuristic; valuation
    and drawdown data are not yet connected. Kept deliberately explainable
    rather than final.

    ``diversification`` is ``None`` when breadth could not be measured. That
    component is then excluded and the same :data:`COMPONENT_BUDGET` is shared
    by the components that remain, so a fund with no holdings file is neither
    rewarded nor punished for the gap. There is no role-based diversification
    default: a guess dressed as a measurement is the defect this design
    removes.
    """
    symbol = row["symbol"]
    text = f"{row['description']} {row['category']}".lower()
    expense = parse_percent(row["gross_expense_ratio"])
    tech = parse_percent(row["information_technology_exposure"])

    role = "Satellite"
    ai_score = 4
    resilience_score = 5

    if any(term in text for term in BOND_TERMS):
        role = "Defensive"
        ai_score = 1
        resilience_score = 9
    elif any(term in text for term in DIVIDEND_TERMS):
        role = "Quality Income"
        ai_score = 5
        resilience_score = 8
    elif any(term in text for term in VALUE_TERMS):
        role = "Value / Fundamental"
        ai_score = 6
        resilience_score = 8
    elif any(term in text for term in CORE_TERMS):
        role = "Foundation"
        ai_score = 8
        resilience_score = 7
    elif any(term in text for term in SECTOR_TERMS):
        role = "Thematic Satellite"
        ai_score = 8 if "technology" in text or "semiconductor" in text else 5
        resilience_score = 3 if ai_score >= 8 else 5

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

    # Renormalize over however many components were actually scored, rather
    # than filling the diversification slot with a value nothing measured.
    components = [ai_score, resilience_score, cost_score]
    if diversification is not None:
        components.append(diversification.score)
    weight_per_point = COMPONENT_BUDGET / (len(components) * COMPONENT_MAX)
    overall = round(sum(components) * weight_per_point + 20)
    overall = max(0, min(100, overall))

    if diversification is None:
        diversification_clause = (
            "diversification not scored (no full holdings file imported; run "
            "atlas import-holdings), so the remaining three components share "
            "the same score budget"
        )
    else:
        diversification_clause = (
            f"diversification={diversification.score}/10 (breadth: "
            f"{diversification.holdings_count:,} holdings from imported file "
            f"covering {diversification.weight_total:.1f}% of the fund)"
        )
    explanation = (
        f"Role={role}; AI={ai_score}/10; resilience={resilience_score}/10; "
        f"{diversification_clause}; cost={cost_score}/10. Cost uses the real "
        "expense ratio and resilience reflects real information-technology "
        "concentration; AI remains heuristic and valuation/drawdown data are "
        "not yet connected."
    )
    return ScoreBreakdown(
        symbol=symbol,
        role=role,
        overall_score=overall,
        ai_score=ai_score,
        resilience_score=resilience_score,
        cost_score=cost_score,
        diversification_score=None if diversification is None else diversification.score,
        explanation=explanation,
    )


def read_scores(conn: sqlite3.Connection) -> list[ScoreBreakdown]:
    """Return previously persisted ETF scores without recomputing them.

    Reads the ``etf_score`` table (populated by :func:`score_all`) so read-only
    callers such as the web dashboard don't have to re-score and re-write on
    every request. A NULL ``diversification_score`` is passed through as
    ``None`` — the fund's breadth was not measured.
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
    rows = conn.execute("SELECT * FROM etf ORDER BY symbol").fetchall()
    scores = [
        score_etf(row, diversification=measured_diversification(conn, row["symbol"]))
        for row in rows
    ]
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
