from __future__ import annotations

from pathlib import Path

import pytest

from atlas.db.database import connect, load_fund_holdings
from atlas.exceptions import AtlasDataError
from atlas.providers.base import FundHolding
from atlas.providers.holdings_file import HoldingsFileProvider

ISHARES = Path("tests/fixtures/holdings_ishares.csv")
SCHWAB = Path("tests/fixtures/holdings_schwab.csv")
INVESCO = Path("tests/fixtures/holdings_invesco.csv")
VANGUARD = Path("tests/fixtures/holdings_vanguard.csv")
FRACTIONS = Path("tests/fixtures/holdings_fractions.csv")


def _by_symbol(holdings: list[FundHolding]) -> dict[str, FundHolding]:
    return {h.holding_symbol: h for h in holdings}


# --- Header detection, preamble/total skipping, cash-row skipping -----------


def test_ishares_header_detected_after_preamble_and_totals_skipped() -> None:
    holdings = list(HoldingsFileProvider(ISHARES).iter_holdings())
    symbols = [h.holding_symbol for h in holdings]
    # Preamble (fund name, as-of date) and trailing "Total" row excluded.
    # Cash row ("--" symbol) excluded too.
    assert symbols == ["NVDA", "AAPL", "MSFT", "GOOGL"]


def test_ishares_cash_row_weight_excluded_from_total() -> None:
    holdings = _by_symbol(list(HoldingsFileProvider(ISHARES).iter_holdings()))
    assert "--" not in holdings
    total = sum(h.weight for h in holdings.values())
    # 6.83 + 6.50 + 6.10 + 3.50 = 22.93; the 0.05 cash row is not counted.
    assert total == pytest.approx(22.93)


def test_ishares_quoted_percent_weight_parses() -> None:
    holdings = _by_symbol(list(HoldingsFileProvider(ISHARES).iter_holdings()))
    assert holdings["NVDA"].weight == pytest.approx(6.83)


def test_schwab_header_detected() -> None:
    holdings = _by_symbol(list(HoldingsFileProvider(SCHWAB).iter_holdings()))
    assert holdings["MSFT"].weight == pytest.approx(6.55)
    assert holdings["MSFT"].holding_name == "Microsoft Corp"


def test_schwab_na_symbol_row_skipped_and_excluded_from_total() -> None:
    holdings = _by_symbol(list(HoldingsFileProvider(SCHWAB).iter_holdings()))
    assert "N/A" not in holdings
    total = sum(h.weight for h in holdings.values())
    # 7.03 (AAPL summed) + 6.55 (MSFT) + 3.40 (AMZN) + 2.10 (GOOG) = 19.08
    assert total == pytest.approx(19.08)


def test_schwab_duplicate_symbol_summed_preserving_first_seen_name() -> None:
    holdings = _by_symbol(list(HoldingsFileProvider(SCHWAB).iter_holdings()))
    assert holdings["AAPL"].weight == pytest.approx(7.03)  # 7.01 + 0.02
    assert holdings["AAPL"].holding_name == "Apple Inc"  # first-seen name kept


def test_invesco_header_detected() -> None:
    holdings = _by_symbol(list(HoldingsFileProvider(INVESCO).iter_holdings()))
    assert holdings["NVDA"].weight == pytest.approx(9.50)
    assert holdings["NVDA"].holding_name == "NVIDIA Corp"


def test_invesco_negative_weight_preserved() -> None:
    holdings = _by_symbol(list(HoldingsFileProvider(INVESCO).iter_holdings()))
    assert holdings["SH"].weight == pytest.approx(-1.20)


def test_vanguard_header_detected_and_holdings_column_does_not_steal_symbol_slot() -> None:
    holdings = list(HoldingsFileProvider(VANGUARD).iter_holdings())
    symbols = [h.holding_symbol for h in holdings]
    # If "Holdings" (the name column) had won the symbol slot, these would be
    # full company names instead of tickers.
    assert symbols == ["MSFT", "AAPL", "NVDA", "AMZN", "GOOGL"]
    by_symbol = _by_symbol(holdings)
    assert by_symbol["MSFT"].holding_name == "Microsoft Corp"
    assert by_symbol["MSFT"].weight == pytest.approx(6.02)


# --- Guards -------------------------------------------------------------


def test_fractions_guard_raises_atlas_data_error() -> None:
    with pytest.raises(AtlasDataError) as excinfo:
        list(HoldingsFileProvider(FRACTIONS).iter_holdings())
    message = str(excinfo.value)
    assert str(FRACTIONS) in message


def test_over_100_guard_raises_atlas_data_error(tmp_path: Path) -> None:
    bad_file = tmp_path / "holdings_over_100.csv"
    bad_file.write_text(
        "Ticker,Name,Weight\n"
        "AAA,Fund Slice A,40.00\n"
        "BBB,Fund Slice B,40.00\n"
        "CCC,Fund Slice C,40.00\n",
        encoding="utf-8",
    )
    with pytest.raises(AtlasDataError) as excinfo:
        list(HoldingsFileProvider(bad_file).iter_holdings())
    message = str(excinfo.value)
    assert str(bad_file) in message


# --- load_fund_holdings persistence --------------------------------------


def test_load_fund_holdings_stores_rows_ranked_by_descending_weight(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    conn.execute("INSERT INTO etf (symbol, description) VALUES ('SCHB', 'Schwab US Broad Market ETF')")
    conn.commit()

    count = load_fund_holdings(conn, "SCHB", SCHWAB)
    assert count == 4  # AAPL, MSFT, AMZN, GOOG (distinct, after dedup)

    rows = conn.execute(
        "SELECT holding_symbol, weight, source, rank FROM etf_holding "
        "WHERE etf_symbol = 'SCHB' ORDER BY rank"
    ).fetchall()
    assert [r["holding_symbol"] for r in rows] == ["AAPL", "MSFT", "AMZN", "GOOG"]
    assert [r["rank"] for r in rows] == [1, 2, 3, 4]
    assert all(r["source"] == "holdings_file" for r in rows)
    assert rows[0]["weight"] == pytest.approx(7.03)


def test_load_fund_holdings_reimport_replaces_not_accumulates(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "SCHB", SCHWAB)
    count = load_fund_holdings(conn, "SCHB", SCHWAB)
    assert count == 4
    total_rows = conn.execute(
        "SELECT COUNT(*) AS c FROM etf_holding WHERE etf_symbol = 'SCHB'"
    ).fetchone()["c"]
    assert total_rows == 4


def test_load_fund_holdings_creates_missing_etf_row(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # SCHB does not exist in the etf table yet.
    assert conn.execute("SELECT 1 FROM etf WHERE symbol = 'SCHB'").fetchone() is None

    count = load_fund_holdings(conn, "SCHB", SCHWAB)
    assert count == 4

    etf_row = conn.execute("SELECT symbol, description FROM etf WHERE symbol = 'SCHB'").fetchone()
    assert etf_row is not None
    assert etf_row["description"] == ""
