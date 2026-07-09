"""Tests for portfolio.analysis hidden-concentration math.

Uses a controlled two-ETF universe so the equal-weight estimate can be
computed by hand:

    AAA holds {X, Y}  (2 holdings)
    BBB holds {X, Z}  (2 holdings)

For a portfolio of AAA and BBB, each holding of an ETF receives
(position_weight / holding_count) of the portfolio.
"""

import sqlite3
from pathlib import Path

import pytest

from atlas.db.database import connect
from atlas.portfolio.analysis import (
    ConcentrationReport,
    combined_concentration,
    portfolio_hidden_concentration,
    summarize_portfolio,
)


def _seed_universe(conn: sqlite3.Connection) -> None:
    for symbol in ("AAA", "BBB"):
        conn.execute(
            "INSERT INTO etf (symbol, description) VALUES (?, ?)",
            (symbol, f"{symbol} test fund"),
        )
    holdings = {"AAA": ["X", "Y"], "BBB": ["X", "Z"]}
    for etf_symbol, symbols in holdings.items():
        for rank, holding in enumerate(symbols, start=1):
            conn.execute(
                "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank) VALUES (?, ?, ?)",
                (etf_symbol, holding, rank),
            )
    conn.commit()


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


def _percent_by_holding(rows) -> dict[str, float]:
    return {row["holding_symbol"]: row["estimated_portfolio_percent"] for row in rows}


def test_equal_weight_concentration_math(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)
    # total 100000: AAA weight 0.6, BBB weight 0.4
    _add_portfolio(conn, "P", [("AAA", 60000, "ETF"), ("BBB", 40000, "ETF")])

    rows = portfolio_hidden_concentration(conn, "P")
    percents = _percent_by_holding(rows)

    # X = 0.6/2 + 0.4/2 = 0.5 ; Y = 0.6/2 = 0.3 ; Z = 0.4/2 = 0.2
    assert percents == {"X": 50.0, "Y": 30.0, "Z": 20.0}


def test_concentration_is_sorted_by_percent_desc(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)
    _add_portfolio(conn, "P", [("AAA", 60000, "ETF"), ("BBB", 40000, "ETF")])

    rows = portfolio_hidden_concentration(conn, "P")

    assert [row["holding_symbol"] for row in rows] == ["X", "Y", "Z"]


def test_concentration_counts_source_positions(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)
    _add_portfolio(conn, "P", [("AAA", 60000, "ETF"), ("BBB", 40000, "ETF")])

    rows = portfolio_hidden_concentration(conn, "P")
    by_holding = {row["holding_symbol"]: row for row in rows}

    # X is reachable via both AAA and BBB; Y only via AAA.
    assert by_holding["X"]["appears_in_positions"] == 2
    assert set(by_holding["X"]["source_etfs"].split(",")) == {"AAA", "BBB"}
    assert by_holding["Y"]["appears_in_positions"] == 1


def test_non_etf_positions_dilute_the_denominator(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)
    # CASH has no parsed holdings, but its value is still part of the total.
    _add_portfolio(
        conn,
        "P",
        [("AAA", 60000, "ETF"), ("BBB", 40000, "ETF"), ("CASH", 100000, "Cash")],
    )

    rows = portfolio_hidden_concentration(conn, "P")
    percents = _percent_by_holding(rows)

    # total is now 200000: X = 0.3/2 + 0.2/2 = 0.25 -> 25%
    assert percents == {"X": 25.0, "Y": 15.0, "Z": 10.0}


def test_zero_total_value_returns_empty_without_dividing_by_zero(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)
    _add_portfolio(conn, "P", [("AAA", 0, "ETF"), ("BBB", 0, "ETF")])

    rows = portfolio_hidden_concentration(conn, "P")

    assert rows == []


def test_missing_portfolio_raises_value_error(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)

    with pytest.raises(ValueError):
        portfolio_hidden_concentration(conn, "does-not-exist")


def test_summarize_splits_equity_fund_and_cash_value(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)
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


def test_combined_concentration_sums_direct_and_lookthrough(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # FUND holds {NVDA, AAPL}; portfolio holds NVDA directly and FUND.
    conn.execute("INSERT INTO etf (symbol, description) VALUES ('FUND', 'A fund')")
    for rank, h in enumerate(["NVDA", "AAPL"], start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank) VALUES ('FUND', ?, ?)",
            (h, rank),
        )
    conn.commit()
    _add_portfolio(conn, "P", [("NVDA", 100, "equity"), ("FUND", 100, "etf")])

    report = combined_concentration(conn, "P")
    by_symbol = {line.symbol: line for line in report.lines}

    assert report.total_value == 200
    # NVDA: 100 direct + 100/2 look-through = 150 -> 75%
    assert by_symbol["NVDA"].exposure_value == 150.0
    assert by_symbol["NVDA"].exposure_percent == 75.0
    assert by_symbol["NVDA"].direct_value == 100.0
    assert by_symbol["NVDA"].lookthrough_value == 50.0
    assert by_symbol["NVDA"].source_funds == ["FUND"]
    # AAPL: 50 look-through only -> 25%
    assert by_symbol["AAPL"].exposure_value == 50.0
    assert by_symbol["AAPL"].direct_value == 0.0
    assert report.unmodeled_fund_value == 0.0


def test_combined_concentration_reports_unmodeled_fund_value(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # FUND has no parsed holdings -> cannot be looked through.
    _add_portfolio(conn, "P", [("NVDA", 100, "equity"), ("FUND", 100, "etf")])

    report = combined_concentration(conn, "P")
    by_symbol = {line.symbol: line for line in report.lines}

    assert by_symbol["NVDA"].exposure_value == 100.0
    assert by_symbol["NVDA"].exposure_percent == 50.0
    assert "FUND" not in by_symbol
    assert report.unmodeled_fund_value == 100.0


def test_combined_concentration_sorted_desc(tmp_path: Path) -> None:
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


def test_combined_concentration_missing_portfolio_raises(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    with pytest.raises(ValueError):
        combined_concentration(conn, "nope")
