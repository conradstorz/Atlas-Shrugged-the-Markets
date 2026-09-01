"""Tests that a fund is scored from evidence or not scored at all (issue #10).

Issue #6 made diversification measured-or-excluded. Cost and resilience still
substituted invented values: no expense ratio gave every fund a mid-scale
``cost_score = 6``, and no information-technology exposure left the role-based
resilience default un-eroded, because the erosion could only ever fire where
the figure existed. Both fallbacks moved a fund's score on the strength of what
Atlas did *not* know.

These tests pin the replacement rule and its consequence: each component is
measured or ``None``, the fixed 80-point budget is shared by whatever remains,
and a fund whose only surviving component is the AI keyword heuristic gets no
overall score at all. Twenty points of base plus one keyword match is not a
score; it is a guess with a number on it, and an investor reads a number as a
measurement.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi.testclient import TestClient
from typer.testing import CliRunner

import atlas.web.app as webapp
from atlas.cli.main import app as cli_app
from atlas.db.database import connect, load_seed_universe
from atlas.reports.markdown import build_research_report
from atlas.scoring.engine import read_scores, score_all

SEED = Path("data/atlas_seed_universe.csv")
runner = CliRunner()


def _add_etf(
    conn: sqlite3.Connection,
    symbol: str,
    description: str = "Total broad market",
    expense: str = "",
    it_exposure: str = "",
) -> None:
    conn.execute(
        "INSERT INTO etf (symbol, description, category, gross_expense_ratio, "
        "information_technology_exposure) VALUES (?, ?, '', ?, ?)",
        (symbol, description, expense, it_exposure),
    )
    conn.commit()


def _add_holdings_file(conn: sqlite3.Connection, symbol: str, holdings_count: int) -> None:
    """Attach a full (100%-covering) imported holdings file of N names."""
    weight = 100.0 / holdings_count
    conn.executemany(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, weight, source) "
        "VALUES (?, ?, ?, ?, 'holdings_file')",
        [(symbol, f"{symbol}H{i:05d}", i, weight) for i in range(1, holdings_count + 1)],
    )
    conn.commit()


def _scored(conn: sqlite3.Connection) -> dict:
    return {score.symbol: score for score in score_all(conn)}


# --- cost is the expense ratio or nothing -------------------------------------

def test_cost_is_not_scored_without_an_expense_ratio(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "NOEXP", it_exposure="10%")

    score = _scored(conn)["NOEXP"]

    assert score.cost_score is None
    assert "cost not scored (no gross expense ratio on file)" in score.explanation


def test_cost_ladder_is_unchanged_where_the_ratio_exists(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    for symbol, expense, expected in [
        ("C10", "0.03%", 10),
        ("C09", "0.10%", 9),
        ("C07", "0.30%", 7),
        ("C05", "0.50%", 5),
        ("C03", "0.95%", 3),
    ]:
        _add_etf(conn, symbol, expense=expense)
        assert _scored(conn)[symbol].cost_score == expected


# --- resilience is the eroded role default or nothing -------------------------

def test_resilience_is_not_scored_without_it_exposure(tmp_path: Path) -> None:
    """The erosion can only fire where the figure exists, so absence is not "low IT"."""
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "NOIT", expense="0.03%")

    score = _scored(conn)["NOIT"]

    assert score.resilience_score is None
    assert "resilience not scored" in score.explanation
    assert "no information-technology exposure on file" in score.explanation


def test_resilience_still_uses_the_role_baseline_where_it_exposure_exists(
    tmp_path: Path,
) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "CALM", expense="0.03%", it_exposure="10%")
    _add_etf(conn, "HOT", expense="0.03%", it_exposure="50%")

    by_symbol = _scored(conn)

    # Foundation baseline 7; 50% IT erodes it by round((50-20)/10) = 3.
    assert by_symbol["CALM"].resilience_score == 7
    assert by_symbol["HOT"].resilience_score == 4


# --- the unscorable fund -------------------------------------------------------

def test_a_fund_with_no_grounded_component_has_no_overall_score(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "BLANK", "Total U.S. stock market")

    score = _scored(conn)["BLANK"]

    assert score.overall_score is None
    assert score.cost_score is None
    assert score.resilience_score is None
    assert score.diversification_score is None
    # Role and AI are keyword heuristics; they survive and are still shown.
    assert score.role == "Foundation"
    assert score.ai_score == 8


def test_the_unscored_explanation_says_so_and_names_the_missing_data(tmp_path: Path) -> None:
    """Article IV: the explanation must state the basis, including its absence."""
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "BLANK", "Total U.S. stock market")

    explanation = _scored(conn)["BLANK"].explanation

    assert explanation.startswith("Not scored:")
    assert "no expense ratio, information-technology exposure, or imported holdings file" in explanation
    assert "Role=Foundation and AI=8/10 are keyword heuristics only" in explanation
    # It must also say what would produce a score.
    assert "atlas import-holdings" in explanation


def test_any_single_grounded_component_is_enough_to_produce_a_score(tmp_path: Path) -> None:
    """Each of the three grounded components on its own lifts a fund out of unscored."""
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "VIACOST", expense="0.03%")
    _add_etf(conn, "VIARESIL", it_exposure="10%")
    _add_etf(conn, "VIADIV")
    _add_holdings_file(conn, "VIADIV", 500)

    by_symbol = _scored(conn)

    assert by_symbol["VIACOST"].overall_score is not None
    assert by_symbol["VIARESIL"].overall_score is not None
    assert by_symbol["VIADIV"].overall_score is not None


# --- renormalization arithmetic, hand-computed --------------------------------

def test_two_scored_components_share_the_whole_budget(tmp_path: Path) -> None:
    """AI 8 + cost 9 over a 2-component budget: 17 * (80 / 20) + 20 = 88."""
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "TWO", expense="0.10%")

    score = _scored(conn)["TWO"]

    assert (score.ai_score, score.cost_score) == (8, 9)
    assert (score.resilience_score, score.diversification_score) == (None, None)
    assert score.overall_score == 88


def test_three_scored_components_share_the_whole_budget(tmp_path: Path) -> None:
    """AI 8 + resilience 7 + cost 9: 24 * (80 / 30) + 20 = 84."""
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "THREE", expense="0.10%", it_exposure="10%")

    score = _scored(conn)["THREE"]

    assert (score.ai_score, score.resilience_score, score.cost_score) == (8, 7, 9)
    assert score.diversification_score is None
    assert score.overall_score == 84


def test_a_fully_evidenced_fund_scores_on_four_components_exactly_as_before(
    tmp_path: Path,
) -> None:
    """Nothing about a fund with all four components may change.

    Foundation role: AI 8. IT 50% erodes resilience 7 by 3, to 4. A 0.10%
    expense ratio is cost 9. A full 500-name holdings file is breadth 7.

        28 * (80 / 40) + 20 = 76
    """
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "FOUR", expense="0.10%", it_exposure="50%")
    _add_holdings_file(conn, "FOUR", 500)

    score = _scored(conn)["FOUR"]

    assert (score.ai_score, score.resilience_score, score.cost_score) == (8, 4, 9)
    assert score.diversification_score == 7
    assert score.overall_score == 76


def test_one_surviving_component_produces_no_score_rather_than_a_number(
    tmp_path: Path,
) -> None:
    """The 1-component case in the same arithmetic series, which has no answer.

    8 * (80 / 10) + 20 would be 84 — a better score than the fully-evidenced
    fund above earns with four real components. That is the number this design
    refuses to emit.
    """
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "ONE")

    assert _scored(conn)["ONE"].overall_score is None


# --- persistence ---------------------------------------------------------------

def test_read_scores_round_trips_every_none(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "BLANK", "Total U.S. stock market")
    _add_etf(conn, "FULL", expense="0.10%", it_exposure="50%")
    _add_holdings_file(conn, "FULL", 500)
    score_all(conn)

    by_symbol = {score.symbol: score for score in read_scores(conn)}
    blank, full = by_symbol["BLANK"], by_symbol["FULL"]

    assert (blank.overall_score, blank.cost_score, blank.resilience_score,
            blank.diversification_score) == (None, None, None, None)
    assert blank.role == "Foundation"
    assert blank.ai_score == 8
    assert blank.explanation.startswith("Not scored:")
    assert (full.overall_score, full.cost_score, full.resilience_score,
            full.diversification_score) == (76, 9, 4, 7)


# --- ranking: an unscored fund goes last, and nothing crashes comparing it -----

def test_score_all_ranks_unscored_funds_last(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "AAABLANK", "Total U.S. stock market")  # sorts first alphabetically
    _add_etf(conn, "MID", expense="0.30%", it_exposure="50%")
    _add_etf(conn, "TOP", expense="0.03%", it_exposure="10%")

    ranked = [score.symbol for score in score_all(conn)]

    assert ranked[-1] == "AAABLANK"
    assert ranked == ["TOP", "MID", "AAABLANK"]


def test_read_scores_ranks_unscored_funds_last(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "AAABLANK", "Total U.S. stock market")
    _add_etf(conn, "TOP", expense="0.03%", it_exposure="10%")
    score_all(conn)

    assert [score.symbol for score in read_scores(conn)] == ["TOP", "AAABLANK"]


# --- every renderer copes with an unscored fund -------------------------------

def test_score_etfs_command_renders_unscored_funds(tmp_path: Path) -> None:
    result = runner.invoke(
        cli_app,
        ["score-etfs", "--seed", str(SEED), "--db", str(tmp_path / "atlas.db"), "--limit", "200"],
    )
    output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "Traceback" not in output
    assert "None" not in output
    assert "no overall score" in output


def test_report_renders_unscored_funds(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "BLANK", "Total U.S. stock market")
    _add_etf(conn, "FULL", expense="0.10%", it_exposure="50%")
    _add_holdings_file(conn, "FULL", 500)

    report = build_research_report(conn)
    scoreboard = report.split("## Most Repeated")[0]

    assert "| 1 | FULL | 76 |" in scoreboard
    assert "| 2 | BLANK | — |" in scoreboard  # unscored, ranked last, dashed
    assert "None" not in scoreboard
    assert "have no overall score" in report


def test_web_etfs_pages_render_unscored_funds(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(webapp, "DEFAULT_DB", tmp_path / "atlas.db")
    monkeypatch.setattr(webapp, "DEFAULT_SEED", SEED)
    monkeypatch.setattr(webapp, "_initialized", False)
    client = TestClient(webapp.app)

    listing = client.get("/etfs?limit=200")

    assert listing.status_code == 200
    assert "<td class='score'>None</td>" not in listing.text
    assert "have no overall score at all" in listing.text

    # VTI carries neither an expense ratio nor an IT exposure in the seed, and
    # has no holdings file, so it is the real universe's unscored case.
    detail = client.get("/etfs/VTI")

    assert detail.status_code == 200
    assert "Not scored" in detail.text
    assert "None</strong> / 100" not in detail.text


# --- the real seed universe ----------------------------------------------------

def test_seed_universe_vti_is_unscored_and_itot_scores_from_real_data(tmp_path: Path) -> None:
    """The reported pair, as the seed actually holds them.

    ITOT carries a 0.03% expense ratio and 35.87% IT exposure, so it scores on
    three real components. VTI carries neither figure and no holdings file, so
    nothing about it is measurable and it is not scored. The gap between them
    is no longer fallback values; it is the difference between having evidence
    and not having any.
    """
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, SEED)
    by_symbol = _scored(conn)

    assert by_symbol["VTI"].overall_score is None
    assert by_symbol["VTI"].cost_score is None
    assert by_symbol["VTI"].resilience_score is None
    assert by_symbol["ITOT"].overall_score == 81
    assert by_symbol["ITOT"].cost_score == 10
    assert by_symbol["ITOT"].resilience_score == 5


def test_no_seed_fund_without_a_ratio_still_reports_a_cost_score(tmp_path: Path) -> None:
    """The deleted `cost_score = 6` fallback must be unreachable, universe-wide.

    Six is still a legal cost score — it is what a real 0.36%-0.60% expense
    ratio earns. What may no longer happen is a fund reporting *any* cost score
    without a ratio behind it.
    """
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, SEED)
    ratios = {
        row["symbol"]: (row["gross_expense_ratio"] or "").strip()
        for row in conn.execute("SELECT symbol, gross_expense_ratio FROM etf")
    }

    scored_without_a_ratio = [
        score.symbol
        for score in score_all(conn)
        if score.cost_score is not None and ratios[score.symbol] in {"", "--"}
    ]

    assert scored_without_a_ratio == []


def test_every_unscored_seed_fund_lacks_all_three_grounded_inputs(tmp_path: Path) -> None:
    """No fund is unscored while Atlas still holds something it could measure."""
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, SEED)

    for score in score_all(conn):
        if score.overall_score is None:
            assert (score.cost_score, score.resilience_score, score.diversification_score) == (
                None,
                None,
                None,
            ), score.symbol
        else:
            # The converse: a scored fund has at least one grounded component.
            assert any(
                component is not None
                for component in (
                    score.cost_score,
                    score.resilience_score,
                    score.diversification_score,
                )
            ), score.symbol
