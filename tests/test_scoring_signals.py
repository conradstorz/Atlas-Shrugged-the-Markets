"""Tests that ETF scores are grounded in real DB data, not fabricated constants.

Diversification is the measured breadth of a fund's holdings, and is measured
only where an imported holdings file covers essentially the whole fund;
elsewhere it is excluded from the score rather than defaulted. Resilience is
eroded by the real parsed information-technology exposure.
"""

import sqlite3
from pathlib import Path

import pytest

from atlas.db.database import connect, load_seed_universe
from atlas.scoring.engine import (
    FULL_COVERAGE_THRESHOLD,
    breadth_score,
    measured_diversification,
    read_scores,
    score_all,
)

SEED = Path("data/atlas_seed_universe.csv")


# --- the breadth scale (pure function) ----------------------------------------

@pytest.mark.parametrize(
    ("holdings", "expected"),
    [(10, 0), (30, 2), (100, 4), (500, 7), (1000, 8), (3000, 10)],
)
def test_breadth_scale_reference_points(holdings: int, expected: int) -> None:
    assert breadth_score(holdings) == expected


def test_breadth_is_clamped_at_both_ends() -> None:
    assert breadth_score(1) == 0  # below the floor
    assert breadth_score(9) == 0
    assert breadth_score(10_000) == 10  # above the ceiling


def test_breadth_of_no_holdings_is_zero_not_an_error() -> None:
    assert breadth_score(0) == 0
    assert breadth_score(-5) == 0


# --- helpers ------------------------------------------------------------------

def _add_etf(
    conn: sqlite3.Connection,
    symbol: str,
    description: str,
    seed_holdings: list[str] | None = None,
    expense: str = "",
    it_exposure: str = "",
) -> None:
    """Insert a fund, optionally with unweighted seed select-list top-ten rows."""
    conn.execute(
        "INSERT INTO etf (symbol, description, category, gross_expense_ratio, "
        "information_technology_exposure) VALUES (?, ?, ?, ?, ?)",
        (symbol, description, "", expense, it_exposure),
    )
    for rank, holding in enumerate(seed_holdings or [], start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank) VALUES (?, ?, ?)",
            (symbol, holding, rank),
        )
    conn.commit()


def _add_holdings_file(
    conn: sqlite3.Connection, symbol: str, holdings_count: int, total_weight: float = 100.0
) -> None:
    """Attach ``holdings_count`` imported rows sharing ``total_weight`` percent."""
    weight = total_weight / holdings_count
    conn.executemany(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, weight, source) "
        "VALUES (?, ?, ?, ?, 'holdings_file')",
        [(symbol, f"{symbol}H{index:05d}", index, weight) for index in range(1, holdings_count + 1)],
    )
    conn.commit()


# --- when is breadth measurable? ----------------------------------------------

def test_full_imported_file_is_measured(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "WIDE", "Total broad market")
    _add_holdings_file(conn, "WIDE", 500)

    measure = measured_diversification(conn, "WIDE")

    assert measure is not None
    assert measure.score == 7
    assert measure.holdings_count == 500
    assert measure.weight_total >= FULL_COVERAGE_THRESHOLD


def test_narrow_full_imported_file_scores_low(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "NARROW", "Some sector fund")
    _add_holdings_file(conn, "NARROW", 65)

    measure = measured_diversification(conn, "NARROW")

    assert measure is not None
    assert measure.score == 3
    assert measure.holdings_count == 65


def test_partial_imported_file_is_not_measured(tmp_path: Path) -> None:
    """A top-ten export is a slice of the fund, not evidence that it holds ten names."""
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "PARTIAL", "Total broad market")
    _add_holdings_file(conn, "PARTIAL", 10, total_weight=35.0)

    assert measured_diversification(conn, "PARTIAL") is None


def test_seed_top_ten_rows_are_not_measured(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "SEEDY", "Total broad market", ["A", "B", "C", "D", "E"])

    assert measured_diversification(conn, "SEEDY") is None


def test_breadth_is_measured_from_the_file_even_when_seed_rows_exist(tmp_path: Path) -> None:
    """Breadth reads the imported file's own coverage, not the top-ten rule.

    Since imports stopped deleting seed rows, a fund can hold both kinds at
    once. Breadth is a property of the holdings file alone: how many names it
    lists and how much of the fund it covers. The presence of a seed top ten
    beside it changes nothing.
    """
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "BOTH", "Total broad market", ["A", "B", "C"])
    _add_holdings_file(conn, "BOTH", 500)

    measure = measured_diversification(conn, "BOTH")

    assert measure is not None
    assert measure.holdings_count == 500


def test_partial_file_beside_seed_rows_is_still_not_measured(tmp_path: Path) -> None:
    """The top-ten rule falls back to the seed list here; breadth stays unknown."""
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "SLICE", "Total broad market", ["A", "B", "C"])
    _add_holdings_file(conn, "SLICE", 10, total_weight=35.0)

    assert measured_diversification(conn, "SLICE") is None


def test_fund_with_no_holdings_at_all_is_not_measured(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "EMPTY", "Total broad market")

    assert measured_diversification(conn, "EMPTY") is None


# --- issue #6: absence of evidence must neither help nor hurt -----------------

MEGA_CAPS = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "GOOG", "META", "TSLA", "MU"]


def test_identical_funds_score_the_same_without_an_imported_holdings_file(tmp_path: Path) -> None:
    """THE regression test for issue #6 — the ITOT/VTI case.

    Two identical total-market funds, neither with an imported holdings file.
    One happens to have seed top-ten rows; the other has none. Nothing about
    the funds differs, so nothing about their scores may differ: missing data
    must neither reward nor punish.
    """
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "HASTEN", "Total U.S. stock market", MEGA_CAPS, it_exposure="35%")
    _add_etf(conn, "NOTOPTEN", "Total U.S. stock market", [], it_exposure="35%")
    # The same mega-caps sit in other funds' top tens, as they do in reality.
    _add_etf(conn, "PEER1", "Large blend fund", MEGA_CAPS[:5])
    _add_etf(conn, "PEER2", "Large blend fund", MEGA_CAPS[5:])

    by_symbol = {score.symbol: score for score in score_all(conn)}

    assert by_symbol["HASTEN"].diversification_score is None
    assert by_symbol["NOTOPTEN"].diversification_score is None
    assert by_symbol["HASTEN"].overall_score == by_symbol["NOTOPTEN"].overall_score


def test_seed_universe_itot_and_vti_share_the_same_diversification_treatment(tmp_path: Path) -> None:
    """The real reported pair: seed top-ten rows are not a breadth measurement.

    ITOT carries seed top-ten rows and VTI carries none. Neither has an
    imported holdings file, so neither fund's breadth is measurable and
    diversification must be excluded from both scores.
    """
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, SEED)

    by_symbol = {score.symbol: score for score in score_all(conn)}

    assert by_symbol["ITOT"].diversification_score is None
    assert by_symbol["VTI"].diversification_score is None


# --- renormalizing the score budget -------------------------------------------

def test_excluding_diversification_reweights_rather_than_substitutes(tmp_path: Path) -> None:
    """Three scored components must spend the same 80-point budget as four.

    Both funds have AI 8, resilience 7 (Foundation baseline, 10% IT exposure
    being below the erosion threshold) and cost 9 (a 0.10% expense ratio).
    MEASURED also has a 1,000-holding file, worth breadth 8 — exactly the mean
    of the other three — so if the budget is renormalized correctly the two
    funds land on the same number:

        three components: 24 * (80 / 30) + 20 = 84
        four components:  32 * (80 / 40) + 20 = 84
    """
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "UNMEASURED", "Total broad market", expense="0.10%", it_exposure="10%")
    _add_etf(conn, "MEASURED", "Total broad market", expense="0.10%", it_exposure="10%")
    _add_holdings_file(conn, "MEASURED", 1000)

    by_symbol = {score.symbol: score for score in score_all(conn)}

    assert (by_symbol["UNMEASURED"].ai_score, by_symbol["UNMEASURED"].resilience_score) == (8, 7)
    assert by_symbol["UNMEASURED"].cost_score == 9
    assert by_symbol["UNMEASURED"].diversification_score is None
    assert by_symbol["MEASURED"].diversification_score == 8
    assert by_symbol["UNMEASURED"].overall_score == 84
    assert by_symbol["MEASURED"].overall_score == 84


def test_a_broader_fund_outscores_a_narrower_one_with_the_same_facts(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "BROAD", "Total broad market", expense="0.10%")
    _add_etf(conn, "TIGHT", "Total broad market", expense="0.10%")
    _add_holdings_file(conn, "BROAD", 3000)
    _add_holdings_file(conn, "TIGHT", 12)

    by_symbol = {score.symbol: score for score in score_all(conn)}

    assert by_symbol["BROAD"].diversification_score == 10
    assert by_symbol["TIGHT"].diversification_score == 0
    # Assert both are scored before comparing them: `None > int` raises
    # TypeError, which would report a scoring regression as a crash instead of
    # a failed assertion.
    assert by_symbol["BROAD"].overall_score is not None
    assert by_symbol["TIGHT"].overall_score is not None
    assert by_symbol["BROAD"].overall_score > by_symbol["TIGHT"].overall_score


# --- the explanation must state its own basis (Constitution Article IV) -------

def test_explanation_states_the_measured_basis_and_count(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "WIDE", "Total broad market")
    _add_holdings_file(conn, "WIDE", 1043)

    score = next(item for item in score_all(conn) if item.symbol == "WIDE")

    assert "diversification=8/10" in score.explanation
    assert "1,043 holdings from imported file" in score.explanation


def test_explanation_says_diversification_was_excluded_and_how_to_fix_it(tmp_path: Path) -> None:
    # The expense ratio keeps the fund scorable, so the explanation is the
    # per-component one rather than the "not scored at all" one. A fund with no
    # measurable component anywhere is covered separately below.
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "BND", "Treasury bond fund", expense="0.03%")

    score = next(item for item in score_all(conn) if item.symbol == "BND")

    assert score.role == "Defensive"
    assert score.diversification_score is None
    assert "diversification not scored" in score.explanation
    assert "atlas import-holdings" in score.explanation
    assert "share the same score budget" in score.explanation


# --- persistence ---------------------------------------------------------------

def test_read_scores_round_trips_an_unmeasured_diversification(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "EMPTY", "Total broad market")
    _add_etf(conn, "WIDE", "Total broad market")
    _add_holdings_file(conn, "WIDE", 500)
    score_all(conn)

    by_symbol = {score.symbol: score for score in read_scores(conn)}

    assert by_symbol["EMPTY"].diversification_score is None
    assert by_symbol["WIDE"].diversification_score == 7


# --- resilience ----------------------------------------------------------------

def test_resilience_erodes_with_real_it_exposure(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "LOWIT", "Total broad market", it_exposure="10%")
    _add_etf(conn, "HIGHIT", "Total broad market", it_exposure="50%")

    by_symbol = {score.symbol: score for score in score_all(conn)}

    # Same role (Foundation, baseline resilience 7). IT 50% -> 7 - (50-20)/10 = 4.
    assert by_symbol["LOWIT"].resilience_score == 7
    assert by_symbol["HIGHIT"].resilience_score == 4
    assert by_symbol["HIGHIT"].resilience_score < by_symbol["LOWIT"].resilience_score


# --- issue #10: cost and resilience stop flattering missing data --------------

def test_itot_and_vti_without_any_evidence_are_both_unscored(tmp_path: Path) -> None:
    """THE regression test for issue #10 — the ITOT/VTI case.

    Two identical total-market funds with no expense ratio, no
    information-technology exposure and no imported holdings file. Every
    data-grounded component is therefore unmeasurable, and the only thing left
    is the AI keyword heuristic. They must produce the same result, and that
    result must be *no score at all* rather than a number assembled from
    fallbacks.
    """
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "ITOT", "Total U.S. stock market", MEGA_CAPS)
    _add_etf(conn, "VTI", "Total U.S. stock market", [])

    by_symbol = {score.symbol: score for score in score_all(conn)}
    itot, vti = by_symbol["ITOT"], by_symbol["VTI"]

    assert itot.overall_score is None
    assert vti.overall_score is None
    assert (itot.overall_score, itot.cost_score, itot.resilience_score,
            itot.diversification_score) == (
        vti.overall_score, vti.cost_score, vti.resilience_score, vti.diversification_score
    )
