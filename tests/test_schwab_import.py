from pathlib import Path

from atlas.db.database import connect
from atlas.portfolio.schwab import load_schwab_positions

FIXTURE = Path("tests/fixtures/schwab_positions_sample.csv")


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
