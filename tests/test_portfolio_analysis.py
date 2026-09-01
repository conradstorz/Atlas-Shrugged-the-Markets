"""Tests for portfolio.analysis: the weighted look-through concentration engine.

`combined_concentration` reports exact math where Atlas has real weighted
fund holdings (`etf_holding.source = 'holdings_file'`) and reports "not
modeled" everywhere else. It never estimates by spreading a fund's value
equally across an unweighted top-ten list.
"""

import sqlite3
from pathlib import Path

import pytest

from atlas.db.database import connect
from atlas.portfolio.analysis import (
    UniverseCoverage,
    combined_concentration,
    summarize_portfolio,
    universe_coverage,
)


def _add_portfolio(conn: sqlite3.Connection, name: str, positions: list[tuple]) -> None:
    """positions: list of (symbol, market_value, asset_type)."""
    conn.execute("INSERT INTO portfolio (name) VALUES (?)", (name,))
    portfolio_id = conn.execute(
        "SELECT id FROM portfolio WHERE name = ?", (name,)
    ).fetchone()["id"]
    for symbol, market_value, asset_type in positions:
        conn.execute(
            "INSERT INTO portfolio_position (portfolio_id, symbol, market_value, asset_type) "
            "VALUES (?, ?, ?, ?)",
            (portfolio_id, symbol, market_value, asset_type),
        )
    conn.commit()


def _add_weighted_holdings(conn: sqlite3.Connection, etf_symbol: str, holdings: list[tuple]) -> None:
    """holdings: list of (holding_symbol, weight_percent). Inserted as source='holdings_file'."""
    conn.execute(
        "INSERT INTO etf (symbol, description) VALUES (?, ?) ON CONFLICT(symbol) DO NOTHING",
        (etf_symbol, f"{etf_symbol} test fund"),
    )
    for rank, (holding_symbol, weight) in enumerate(holdings, start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, weight, source) "
            "VALUES (?, ?, ?, ?, 'holdings_file')",
            (etf_symbol, holding_symbol, rank, weight),
        )
    conn.commit()


def _add_seed_holdings(conn: sqlite3.Connection, etf_symbol: str, holding_symbols: list[str]) -> None:
    """Seed top-ten membership rows: no weight, source='seed_top_ten'."""
    conn.execute(
        "INSERT INTO etf (symbol, description) VALUES (?, ?) ON CONFLICT(symbol) DO NOTHING",
        (etf_symbol, f"{etf_symbol} test fund"),
    )
    for rank, holding_symbol in enumerate(holding_symbols, start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source) "
            "VALUES (?, ?, ?, 'seed_top_ten')",
            (etf_symbol, holding_symbol, rank),
        )
    conn.commit()


def _build_worked_example(conn: sqlite3.Connection) -> None:
    """The brief's worked example: NVDA direct, SCHB weighted, SCHD seed-only, CASH.

    Total portfolio value $100,000.
    """
    _add_weighted_holdings(
        conn,
        "SCHB",
        [("NVDA", 7.00), ("AAPL", 6.00), ("MSFT", 5.00)],
    )
    _add_seed_holdings(conn, "SCHD", ["XOM"])
    _add_portfolio(
        conn,
        "P",
        [
            ("NVDA", 10000, "equity"),
            ("SCHB", 50000, "etf"),
            ("SCHD", 25000, "etf"),
            ("CASH", 15000, "cash"),
        ],
    )


def test_summarize_splits_equity_fund_and_cash_value(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_portfolio(
        conn,
        "P",
        [("AAA", 60000, "etf"), ("NVDA", 40000, "equity"), ("CASH", 100000, "cash")],
    )

    summary = summarize_portfolio(conn, "P")

    assert summary.position_count == 3
    assert summary.total_value == 200000
    assert summary.equity_value == 40000
    assert summary.fund_value == 60000
    assert summary.cash_value == 100000


def test_combined_concentration_worked_example(tmp_path: Path) -> None:
    """The brief's primary worked example, matched to the hand-computed figures."""
    conn = connect(tmp_path / "atlas.db")
    _build_worked_example(conn)

    report = combined_concentration(conn, "P")
    by_symbol = {line.symbol: line for line in report.lines}

    # NVDA is held both directly and inside SCHB's weighted look-through, and
    # must be summed into a single line.
    assert by_symbol["NVDA"].exposure_value == 13500.00
    assert by_symbol["NVDA"].direct_value == 10000.00
    assert by_symbol["NVDA"].lookthrough_value == 3500.00
    assert by_symbol["NVDA"].exposure_percent == 13.50
    assert by_symbol["NVDA"].source_funds == ["SCHB"]

    assert by_symbol["AAPL"].exposure_value == 3000.00
    assert by_symbol["AAPL"].direct_value == 0.00
    assert by_symbol["AAPL"].lookthrough_value == 3000.00
    assert by_symbol["AAPL"].exposure_percent == 3.00

    assert by_symbol["MSFT"].exposure_value == 2500.00
    assert by_symbol["MSFT"].direct_value == 0.00
    assert by_symbol["MSFT"].lookthrough_value == 2500.00
    assert by_symbol["MSFT"].exposure_percent == 2.50

    # SCHD is seed-only (no weights): it contributes nothing to lines.
    assert "XOM" not in by_symbol
    assert "SCHD" not in by_symbol

    assert report.total_value == 100000.00
    assert report.modeled_value == 19000.00
    assert report.unmodeled_fund_value == 66000.00
    assert report.cash_value == 15000.00
    assert report.other_value == 0.00

    assert report.total_value == pytest.approx(
        report.modeled_value + report.unmodeled_fund_value + report.cash_value + report.other_value
    )

    coverage_by_symbol = {fc.symbol: fc for fc in report.fund_coverage}
    assert [fc.symbol for fc in report.fund_coverage] == ["SCHB", "SCHD"]  # sorted by market_value desc

    schb = coverage_by_symbol["SCHB"]
    assert schb.market_value == 50000.00
    assert schb.has_weights is True
    assert schb.modeled_share == pytest.approx(0.18)
    assert schb.modeled_value == 9000.00

    schd = coverage_by_symbol["SCHD"]
    assert schd.market_value == 25000.00
    assert schd.has_weights is False
    assert schd.modeled_share == 0.0
    assert schd.modeled_value == 0.0

    # Lines sorted by exposure_percent desc, symbol asc tiebreak.
    assert [line.symbol for line in report.lines] == ["NVDA", "AAPL", "MSFT"]


def test_seed_only_fund_reports_nothing_but_unmodeled_value(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_seed_holdings(conn, "SCHD", ["XOM", "JNJ"])
    _add_portfolio(conn, "P", [("SCHD", 25000, "etf")])

    report = combined_concentration(conn, "P")

    assert report.lines == []
    assert report.unmodeled_fund_value == 25000.00
    assert report.modeled_value == 0.00


def test_fund_with_no_holdings_at_all_is_fully_unmodeled(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_portfolio(conn, "P", [("NVDA", 100, "equity"), ("FUND", 100, "etf")])

    report = combined_concentration(conn, "P")
    by_symbol = {line.symbol: line for line in report.lines}

    assert by_symbol["NVDA"].exposure_value == 100.0
    assert "FUND" not in by_symbol
    assert report.unmodeled_fund_value == 100.0
    assert report.modeled_value == 100.0

    coverage_by_symbol = {fc.symbol: fc for fc in report.fund_coverage}
    assert coverage_by_symbol["FUND"].has_weights is False
    assert coverage_by_symbol["FUND"].modeled_share == 0.0
    assert coverage_by_symbol["FUND"].modeled_value == 0.0


def test_other_asset_type_reported_separately_and_invariant_holds(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_portfolio(
        conn,
        "P",
        [
            ("NVDA", 10000, "equity"),
            ("BOND-FUND", 5000, "other"),
            ("CASH", 5000, "cash"),
        ],
    )

    report = combined_concentration(conn, "P")

    assert report.other_value == 5000.00
    assert report.total_value == pytest.approx(
        report.modeled_value + report.unmodeled_fund_value + report.cash_value + report.other_value
    )


def test_fund_near_full_weight_coverage_leaves_near_zero_unmodeled(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_weighted_holdings(
        conn,
        "TOTAL",
        [("A", 40.00), ("B", 35.00), ("C", 24.99)],  # sums to 99.99%
    )
    _add_portfolio(conn, "P", [("TOTAL", 10000, "etf")])

    report = combined_concentration(conn, "P")

    coverage = {fc.symbol: fc for fc in report.fund_coverage}["TOTAL"]
    assert coverage.modeled_share == pytest.approx(0.9999)
    assert report.unmodeled_fund_value == pytest.approx(1.0, abs=0.01)


def test_lines_sorted_by_exposure_percent_desc_symbol_tiebreak(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_portfolio(conn, "P", [("NVDA", 100, "equity"), ("AAPL", 300, "equity")])

    report = combined_concentration(conn, "P")

    assert [line.symbol for line in report.lines] == ["AAPL", "NVDA"]


def test_combined_concentration_zero_total_is_empty(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_portfolio(conn, "P", [("NVDA", 0, "equity")])

    report = combined_concentration(conn, "P")

    assert report.lines == []
    assert report.total_value == 0.0
    assert report.modeled_value == 0.0
    assert report.unmodeled_fund_value == 0.0
    assert report.cash_value == 0.0
    assert report.other_value == 0.0
    assert report.fund_coverage == []


def test_combined_concentration_negative_total_is_empty(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_portfolio(conn, "P", [("NVDA", -100, "equity")])

    report = combined_concentration(conn, "P")

    assert report.lines == []
    assert report.total_value == 0.0


def test_combined_concentration_missing_portfolio_raises(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    with pytest.raises(ValueError):
        combined_concentration(conn, "nope")


def test_lookthrough_accumulates_across_multiple_funds(tmp_path: Path) -> None:
    """One symbol reached through two different weighted funds must sum its
    contributions into a single line and list every contributing fund."""
    conn = connect(tmp_path / "atlas.db")
    _add_weighted_holdings(conn, "F1", [("NVDA", 10.0)])
    _add_weighted_holdings(conn, "F2", [("NVDA", 20.0)])
    _add_portfolio(
        conn,
        "P",
        [("F1", 1000, "etf"), ("F2", 1000, "etf")],
    )

    report = combined_concentration(conn, "P")
    by_symbol = {line.symbol: line for line in report.lines}

    assert by_symbol["NVDA"].lookthrough_value == 300.00
    assert by_symbol["NVDA"].direct_value == 0.00
    assert by_symbol["NVDA"].source_funds == ["F1", "F2"]


# --- universe_coverage ----------------------------------------------------


def test_universe_coverage_partitions_total_funds_exactly(tmp_path: Path) -> None:
    """One weighted fund, one seed-only fund, one fund with no holdings rows
    at all: totals must partition exactly, per the brief's requirement."""
    conn = connect(tmp_path / "atlas.db")
    _add_weighted_holdings(conn, "WEIGHTED", [("A", 10.0)])
    _add_seed_holdings(conn, "SEEDONLY", ["B"])
    conn.execute("INSERT INTO etf (symbol, description) VALUES ('BARE', 'no holdings fund')")
    conn.commit()

    coverage = universe_coverage(conn)

    assert isinstance(coverage, UniverseCoverage)
    assert coverage.total_funds == 3
    assert coverage.weighted_funds == 1
    assert coverage.membership_only_funds == 1
    assert coverage.no_holdings_funds == 1
    assert (
        coverage.weighted_funds + coverage.membership_only_funds + coverage.no_holdings_funds
        == coverage.total_funds
    )


def test_universe_coverage_empty_universe(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")

    coverage = universe_coverage(conn)

    assert coverage.total_funds == 0
    assert coverage.weighted_funds == 0
    assert coverage.membership_only_funds == 0
    assert coverage.no_holdings_funds == 0


def test_universe_coverage_fund_with_only_holdings_file_rows_is_weighted_not_membership(
    tmp_path: Path,
) -> None:
    """A fund whose only etf_holding rows are source='holdings_file' must not
    also be double-counted as membership-only."""
    conn = connect(tmp_path / "atlas.db")
    _add_weighted_holdings(conn, "WEIGHTED", [("A", 10.0), ("B", 20.0)])

    coverage = universe_coverage(conn)

    assert coverage.total_funds == 1
    assert coverage.weighted_funds == 1
    assert coverage.membership_only_funds == 0
    assert coverage.no_holdings_funds == 0


def test_weights_summing_over_100_do_not_overmodel_the_position(tmp_path: Path) -> None:
    """A file rounding to just over 100% must not model more than the position.

    The ingest guard admits totals up to 100.5, so taken literally a 100.30%
    file would report $10,030 modeled against a $10,000 position, 100.30%
    coverage, and a negative unmodeled remainder. The surplus is rounding
    noise in the issuer's own weights, not exposure.
    """
    conn = connect(tmp_path / "atlas.db")
    _add_weighted_holdings(conn, "XYZ", [("AAA", 50.20), ("BBB", 50.10)])
    _add_portfolio(conn, "P", [("XYZ", 10000, "etf")])

    report = combined_concentration(conn, "P")

    coverage = report.fund_coverage[0]
    assert coverage.modeled_share == 1.0
    assert coverage.modeled_value == 10000.00
    assert report.modeled_value == pytest.approx(10000.00)
    assert report.unmodeled_fund_value == 0.00
    assert report.unmodeled_fund_value >= 0.0
    # Contributions stay proportional to the issuer's relative weights.
    by_symbol = {line.symbol: line for line in report.lines}
    assert by_symbol["AAA"].lookthrough_value == pytest.approx(5004.99, abs=0.01)
    assert by_symbol["BBB"].lookthrough_value == pytest.approx(4995.01, abs=0.01)
    assert sum(line.lookthrough_value for line in report.lines) == pytest.approx(10000.00, abs=0.01)
    assert report.modeled_value + report.unmodeled_fund_value + report.cash_value + report.other_value == pytest.approx(report.total_value)


def test_weights_summing_under_100_still_leave_a_real_remainder(tmp_path: Path) -> None:
    """Normalization must apply ONLY to the over-100 case.

    A partial holdings file (a top-ten export, say) genuinely models only part
    of the fund; scaling it up to 100% would reinvent the equal-weight lie.
    """
    conn = connect(tmp_path / "atlas.db")
    _add_weighted_holdings(conn, "XYZ", [("AAA", 12.00), ("BBB", 6.00)])
    _add_portfolio(conn, "P", [("XYZ", 10000, "etf")])

    report = combined_concentration(conn, "P")

    assert report.fund_coverage[0].modeled_share == pytest.approx(0.18)
    assert report.modeled_value == pytest.approx(1800.00)
    assert report.unmodeled_fund_value == pytest.approx(8200.00)
