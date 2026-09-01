from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from math import log10

from atlas.analytics.overlap import FULL_COVERAGE_THRESHOLD
from atlas.parsing import parse_percent
from atlas.scoring.model import ScoreBreakdown, score_sort_key

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
# whole fund; a partial file means breadth is unknown, not small. The same
# threshold decides whether such a file supersedes a fund's seed top ten, so it
# is defined once, in `atlas.analytics.overlap` — the lower-level of the two
# rules — and imported here rather than restated. Importing it also keeps
# `from atlas.scoring.engine import FULL_COVERAGE_THRESHOLD` working for
# callers that already looked for it here.

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
    the fund has imported holdings-file rows (``source='holdings_file'``) whose
    weights total at least :data:`FULL_COVERAGE_THRESHOLD` percent of the fund.

    Seed rows are top-ten *membership*, not a holdings list, and a partial
    issuer export is a slice of the fund. Counting either as breadth would
    report every seed fund — including a total-market index — as holding ten
    names, which is a worse lie than saying nothing.

    This asks the imported file about its own coverage rather than asking
    :func:`~atlas.analytics.overlap.holdings_weight_source` which list the
    fund's *top ten* is drawn from. The two questions have different answers
    now that both sources can sit on one fund: a fund whose top ten comes from
    its seed list can still have a full holdings file behind it, and a fund
    with no seed rows reports a partial file as its top-ten source without that
    file being enough to measure breadth from.
    """
    symbol = etf_symbol.upper()
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
    """Generate a transparent, fully data-grounded score for an ETF, or none.

    Every component is measured or excluded; none is substituted with a
    stand-in value. Cost comes from the real gross expense ratio, resilience is
    a role-based default eroded by the real information-technology exposure,
    and diversification is the measured breadth of the fund's imported holdings
    file (passed in via ``diversification``). Any of the three is ``None`` when
    its input is absent, and the same fixed :data:`COMPONENT_BUDGET` is then
    shared by the components that remain, so missing data neither rewards nor
    punishes a fund. The AI signal remains a keyword heuristic; valuation and
    drawdown data are not yet connected.

    **A fund with no grounded component at all has no overall score**:
    ``overall_score`` is ``None``. The base of 20 plus a single keyword-derived
    component would produce a confident-looking number from nothing the data
    supports — a guess with a number on it, which is exactly what an investor
    would read as a measurement. ``role`` and ``ai_score`` are still reported,
    because they remain worth showing, and the explanation says plainly that no
    score was produced and what data would produce one.
    """
    symbol = row["symbol"]
    text = f"{row['description']} {row['category']}".lower()
    expense = parse_percent(row["gross_expense_ratio"])
    tech = parse_percent(row["information_technology_exposure"])

    # The role keyword defaults still seed resilience. They are the starting
    # point for the erosion below, not a score in themselves: the value only
    # reaches the breakdown once real IT-exposure data has acted on it.
    role = "Satellite"
    ai_score = 4
    resilience_baseline = 5

    if any(term in text for term in BOND_TERMS):
        role = "Defensive"
        ai_score = 1
        resilience_baseline = 9
    elif any(term in text for term in DIVIDEND_TERMS):
        role = "Quality Income"
        ai_score = 5
        resilience_baseline = 8
    elif any(term in text for term in VALUE_TERMS):
        role = "Value / Fundamental"
        ai_score = 6
        resilience_baseline = 8
    elif any(term in text for term in CORE_TERMS):
        role = "Foundation"
        ai_score = 8
        resilience_baseline = 7
    elif any(term in text for term in SECTOR_TERMS):
        role = "Thematic Satellite"
        ai_score = 8 if "technology" in text or "semiconductor" in text else 5
        resilience_baseline = 3 if ai_score >= 8 else 5

    # AI signal is nudged up by real information-technology concentration.
    if tech is not None:
        if tech >= 40:
            ai_score = max(ai_score, 8)
        elif tech >= 20:
            ai_score = max(ai_score, 7)

    # Resilience erodes with real IT concentration: every 10 percentage points
    # of technology exposure above 20% costs one point of resilience.
    #
    # The erosion can only ever fire where the figure exists, so reporting the
    # un-eroded role default for a fund with no IT exposure on file silently
    # asserted "this fund is not technology-concentrated" — an opinion with no
    # evidence behind it, which flattered precisely the funds Atlas knows least
    # about. Unknown IT exposure now means no resilience score.
    resilience_score: int | None
    if tech is None:
        resilience_score = None
    elif tech > 20:
        resilience_score = max(1, resilience_baseline - round((tech - 20) / 10))
    else:
        resilience_score = resilience_baseline

    # Cost is the real expense ratio or nothing. The former `cost_score = 6`
    # fallback was a mid-scale invention that punished a genuinely cheap fund
    # whose ratio Atlas happened to lack and flattered an expensive one.
    cost_score: int | None
    if expense is None:
        cost_score = None
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

    diversification_score = None if diversification is None else diversification.score

    # Renormalize over however many components were actually measured, rather
    # than filling an empty slot with a value nothing measured.
    #
    # Only these three count as grounded: each rests on a figure about this
    # particular fund. `ai_score` is deliberately excluded from the test —
    # it is keyword-matched from the description, which every fund has, so its
    # presence is evidence of nothing. When no grounded component survives, the
    # AI heuristic is all that is left and no overall score is produced at all.
    grounded = [
        score
        for score in (resilience_score, cost_score, diversification_score)
        if score is not None
    ]
    overall: int | None
    if not grounded:
        overall = None
    else:
        components = [ai_score, *grounded]
        weight_per_point = COMPONENT_BUDGET / (len(components) * COMPONENT_MAX)
        overall = max(0, min(100, round(sum(components) * weight_per_point + 20)))

    explanation = _explain(
        role=role,
        ai_score=ai_score,
        resilience_score=resilience_score,
        resilience_baseline=resilience_baseline,
        tech=tech,
        cost_score=cost_score,
        expense_text=row["gross_expense_ratio"],
        diversification=diversification,
        overall=overall,
        scored_component_count=len(grounded) + 1,
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


def _explain(
    *,
    role: str,
    ai_score: int,
    resilience_score: int | None,
    resilience_baseline: int,
    tech: float | None,
    cost_score: int | None,
    expense_text: str | None,
    diversification: DiversificationMeasure | None,
    overall: int | None,
    scored_component_count: int,
) -> str:
    """Write a score's own rationale, component by component.

    The Constitution requires a score to decompose into its components, their
    weights, the raw inputs behind them and a rationale (Article IV), and
    requires an opinion to be tied to evidence or to an explicit assumption
    (Article VIII). So every component states either its value *and the raw
    figure it came from*, or that it was not scored *and why*. A fund with no
    overall score says so outright and names the data that would produce one,
    rather than reporting a number nothing supports.
    """
    if overall is None:
        return (
            "Not scored: no expense ratio, no information-technology exposure, and "
            f"no holdings file covering at least {FULL_COVERAGE_THRESHOLD:g}% of the "
            f"fund. Role={role} and AI={ai_score}/10 are keyword heuristics only. "
            "A gross expense ratio, an information-technology exposure figure, or a "
            "full holdings file (atlas import-holdings) would each produce a score."
        )

    if resilience_score is None:
        resilience_clause = (
            "resilience not scored (no information-technology exposure on file, so "
            f"the {role} baseline of {resilience_baseline}/10 could not be tested "
            "against real data)"
        )
    elif tech is not None and tech > 20:
        resilience_clause = (
            f"resilience={resilience_score}/10 ({role} baseline {resilience_baseline}/10 "
            f"eroded by {tech:g}% information-technology exposure)"
        )
    else:
        resilience_clause = (
            f"resilience={resilience_score}/10 ({role} baseline, undisturbed by "
            f"{tech:g}% information-technology exposure)"
        )

    if diversification is None:
        # True whether no file was imported at all or an imported one covers too
        # little of the fund: the clause states the condition that is unmet, not
        # an assumption about what the investor did. Telling someone who
        # imported a partial file that they imported nothing would send them to
        # re-run a command they already ran.
        diversification_clause = (
            "diversification not scored (no holdings file covering at least "
            f"{FULL_COVERAGE_THRESHOLD:g}% of the fund; run atlas import-holdings "
            "with a full issuer holdings file), so the remaining components share "
            "the same score budget"
        )
    else:
        diversification_clause = (
            f"diversification={diversification.score}/10 (breadth: "
            f"{diversification.holdings_count:,} holdings from imported file "
            f"covering {diversification.weight_total:.1f}% of the fund)"
        )

    if cost_score is None:
        cost_clause = "cost not scored (no gross expense ratio on file)"
    else:
        cost_clause = f"cost={cost_score}/10 ({expense_text} gross expense ratio)"

    return (
        f"Role={role}; AI={ai_score}/10 (keyword heuristic); {resilience_clause}; "
        f"{diversification_clause}; {cost_clause}. Overall {overall}/100: "
        f"{scored_component_count} scored components share the "
        f"{COMPONENT_BUDGET:g}-point budget above a base of 20; an unscored "
        "component is excluded, never substituted. AI remains heuristic and "
        "valuation/drawdown data are not yet connected."
    )


def read_scores(conn: sqlite3.Connection) -> list[ScoreBreakdown]:
    """Return previously persisted ETF scores without recomputing them.

    Reads the ``etf_score`` table (populated by :func:`score_all`) so read-only
    callers such as the web dashboard don't have to re-score and re-write on
    every request. Every NULL is passed through as ``None`` rather than
    defaulted: an unmeasured component, or — for ``overall_score`` — a fund
    with no data-grounded component to score at all.

    Unscored funds sort last. SQLite orders NULL below every value, so a
    plain ``DESC`` would already do it, but the ordering is stated explicitly
    here because it is a deliberate decision (Atlas has no basis for ranking a
    fund it could not score) rather than a property of the storage engine.
    """
    rows = conn.execute(
        """
        SELECT symbol, role, overall_score, ai_score, resilience_score,
               cost_score, diversification_score, explanation
        FROM etf_score
        ORDER BY overall_score IS NULL, overall_score DESC, symbol
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
    """Score every fund in ``etf``, persist the results, and rank them.

    Returns the scores ranked best-first, with funds that could not be scored
    at all last. ``None`` components and a ``None`` ``overall_score`` are
    written to ``etf_score`` as SQL NULL, which is what those columns mean.
    """
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
    # `score_sort_key` rather than `reverse=True`: an unscored fund's None
    # cannot be compared with an int, and it belongs at the bottom of the
    # ranking rather than wherever a comparison happens to put it. The sort is
    # stable and the input is symbol-ordered, so ties keep symbol order.
    return sorted(scores, key=lambda item: score_sort_key(item.overall_score))
