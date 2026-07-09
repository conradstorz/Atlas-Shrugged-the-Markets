from pathlib import Path

from atlas.db.database import connect
from atlas.portfolio.analysis import combined_concentration
from atlas.portfolio.schwab import load_schwab_positions

FIXTURE = Path("tests/fixtures/schwab_positions_sample.csv")
MULTI_FIXTURE = Path("tests/fixtures/schwab_positions_multi_account.csv")


def test_import_counts_positions_and_skips_preamble_and_total(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    count = load_schwab_positions(conn, "Primary", FIXTURE)
    # NVDA, GILD, SCHD, FSELX, CASH -> 5. Preamble and "Positions Total" skipped.
    assert count == 5


def test_import_normalizes_asset_types_and_values(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_schwab_positions(conn, "Primary", FIXTURE)
    rows = {
        r["symbol"]: r
        for r in conn.execute(
            "SELECT symbol, asset_type, market_value FROM portfolio_position"
        ).fetchall()
    }

    assert rows["NVDA"]["asset_type"] == "equity"
    assert rows["NVDA"]["market_value"] == 10410.12
    assert rows["SCHD"]["asset_type"] == "etf"
    assert rows["FSELX"]["asset_type"] == "mutual_fund"
    assert rows["CASH"]["asset_type"] == "cash"
    assert rows["CASH"]["market_value"] == 27.81


def test_reimport_replaces_existing_positions(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_schwab_positions(conn, "Primary", FIXTURE)
    load_schwab_positions(conn, "Primary", FIXTURE)
    count = conn.execute("SELECT COUNT(*) AS c FROM portfolio_position").fetchone()["c"]
    assert count == 5


def test_multi_account_sums_recurring_symbols(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    count = load_schwab_positions(conn, "Primary", MULTI_FIXTURE)
    rows = {
        r["symbol"]: r["market_value"]
        for r in conn.execute(
            "SELECT symbol, market_value FROM portfolio_position"
        ).fetchall()
    }
    # Distinct stored symbols: NVDA, GILD, CASH, AAPL
    assert count == 4
    assert rows["NVDA"] == 17000.0  # 10000 (acct 1) + 7000 (acct 2), summed
    assert rows["CASH"] == 150.0    # 100 + 50
    assert rows["GILD"] == 5000.0
    assert rows["AAPL"] == 2000.0


def test_schwab_import_feeds_combined_concentration(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # Give SCHD parsed holdings so it is looked through; FSELX has none.
    conn.execute("INSERT INTO etf (symbol, description) VALUES ('SCHD', 'Schwab Dividend')")
    for rank, holding in enumerate(["KO", "PEP"], start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank) VALUES ('SCHD', ?, ?)",
            (holding, rank),
        )
    conn.commit()

    load_schwab_positions(conn, "Play", FIXTURE)
    report = combined_concentration(conn, "Play")
    by_symbol = {line.symbol: line for line in report.lines}

    assert by_symbol["GILD"].direct_value == 16977.50
    assert by_symbol["NVDA"].direct_value == 10410.12
    # SCHD $2,942.94 split equally across KO/PEP -> 1471.47 each
    assert by_symbol["KO"].lookthrough_value == 1471.47
    # FSELX $8,184.69 has no holdings -> unmodeled
    assert report.unmodeled_fund_value == 8184.69
