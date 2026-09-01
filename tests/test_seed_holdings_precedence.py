from __future__ import annotations

from pathlib import Path

from atlas.db.database import connect, load_fund_holdings, load_seed_universe

SEED = Path("data/atlas_seed_universe.csv")
INVESCO = Path("tests/fixtures/holdings_invesco.csv")

# DIVB carries a real ten-symbol seed_top_ten list in the seed universe CSV,
# so it is a genuine case of "seed data present, then real data imported".
DIVB_SEED_TOP_TEN = ["ADP", "IBM", "ACN", "JPM", "PAYX", "JNJ", "HPQ", "XOM", "ABBV", "CTSH"]


def test_imported_holdings_survive_reseed(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "DIVB", INVESCO)
    load_seed_universe(conn, SEED)  # must not flip holdings_file rows back to seed_top_ten

    rows = conn.execute(
        "SELECT holding_symbol, weight, source FROM etf_holding WHERE etf_symbol = 'DIVB' ORDER BY rank"
    ).fetchall()
    symbols = [r["holding_symbol"] for r in rows]
    assert symbols == ["NVDA", "AAPL", "MSFT", "AMZN", "META", "SH"]
    assert all(r["source"] == "holdings_file" for r in rows)
    assert rows[0]["weight"] == 9.50
    assert rows[-1]["weight"] == -1.20


def test_funds_without_imported_holdings_still_get_seed_top_ten(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # Only DIVB has real imported holdings; every other fund, including BNDW,
    # should still receive its seed_top_ten rows normally.
    load_fund_holdings(conn, "DIVB", INVESCO)
    load_seed_universe(conn, SEED)

    bndw_rows = conn.execute(
        "SELECT holding_symbol, source FROM etf_holding WHERE etf_symbol = 'BNDW' ORDER BY rank"
    ).fetchall()
    assert [r["holding_symbol"] for r in bndw_rows] == ["BND", "BNDX"]
    assert all(r["source"] == "seed_top_ten" for r in bndw_rows)

    divb_rows = conn.execute(
        "SELECT source FROM etf_holding WHERE etf_symbol = 'DIVB'"
    ).fetchall()
    assert all(r["source"] == "holdings_file" for r in divb_rows)


def test_etf_metadata_row_still_updates_on_reseed(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "DIVB", INVESCO)
    # Before reseed, load_fund_holdings only inserted a minimal etf row.
    before = conn.execute("SELECT description FROM etf WHERE symbol = 'DIVB'").fetchone()
    assert before["description"] == ""

    load_seed_universe(conn, SEED)

    after = conn.execute("SELECT description, fund_type FROM etf WHERE symbol = 'DIVB'").fetchone()
    assert after["description"] == "iShares Core Dividend ETF"
    assert after["fund_type"] == "ETF"
