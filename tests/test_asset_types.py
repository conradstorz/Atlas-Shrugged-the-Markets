from __future__ import annotations

import pytest

from atlas.db.database import connect, forget_fund, load_fund_holdings, load_seed_universe
from atlas.exceptions import AtlasDataError

SEED_HEADER = (
    "Symbol,Description,Fund Type,ETF Select List® Category,ETF Select List,"
    "Top Ten Holdings,Gross Expense Ratio,Sector Exposure: Information Technology,Source\n"
)


def write_seed_csv(tmp_path, *rows: str):
    """One seed row per string, matching data/atlas_seed_universe.csv's columns."""
    path = tmp_path / "seed.csv"
    path.write_text(SEED_HEADER + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def write_holdings_csv(tmp_path, name: str, *rows: tuple[str, str, float]):
    """(ticker, holding_name, weight_percent) rows in an issuer-file shape."""
    path = tmp_path / name
    lines = ["Ticker,Name,Weight\n"]
    lines += [f"{ticker},{holding_name},{weight}\n" for ticker, holding_name, weight in rows]
    path.write_text("".join(lines), encoding="utf-8")
    return path


def test_seed_import_promotes_held_symbol_to_fund(tmp_path):
    conn = connect(tmp_path / "atlas.db")
    # 1. Import holdings for SOMEFUND whose file names VTI -> VTI becomes a company stub.
    load_fund_holdings(
        conn, "SOMEFUND", write_holdings_csv(tmp_path, "somefund.csv", ("VTI", "Vanguard Total", 12.0))
    )
    assert conn.execute("SELECT asset_type FROM asset WHERE symbol='VTI'").fetchone()[0] == "company"
    # 2. Seed CSV listing VTI as a fund arrives.
    load_seed_universe(
        conn,
        write_seed_csv(tmp_path, "VTI,Vanguard Total Stock Market ETF,ETF,Large Blend,Yes,--,0.03%,--,Seed"),
    )
    assert conn.execute("SELECT asset_type FROM asset WHERE symbol='VTI'").fetchone()[0] == "fund"
    assert conn.execute("SELECT 1 FROM company WHERE symbol='VTI'").fetchone() is None
    assert conn.execute("SELECT 1 FROM fund WHERE symbol='VTI'").fetchone()
    # SOMEFUND's holding row referencing VTI survives the promotion.
    assert conn.execute(
        "SELECT 1 FROM fund_holding WHERE fund_symbol='SOMEFUND' AND holding_symbol='VTI'"
    ).fetchone()


def test_import_holdings_for_company_symbol_refuses(tmp_path):
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(
        conn, "SOMEFUND", write_holdings_csv(tmp_path, "somefund.csv", ("NVDA", "NVIDIA Corp", 7.5))
    )  # NVDA -> company stub
    with pytest.raises(AtlasDataError, match="NVDA"):
        load_fund_holdings(
            conn, "NVDA", write_holdings_csv(tmp_path, "nvda.csv", ("AAPL", "Apple Inc", 3.0))
        )
    # Nothing was written for NVDA-as-fund.
    assert conn.execute("SELECT 1 FROM fund WHERE symbol='NVDA'").fetchone() is None
    assert conn.execute(
        "SELECT COUNT(*) FROM fund_holding WHERE fund_symbol='NVDA'"
    ).fetchone()[0] == 0


def test_forget_fund_removes_orphaned_company_stubs(tmp_path):
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(
        conn, "FUNDA", write_holdings_csv(tmp_path, "funda.csv", ("ZZZQ", "Exclusive Co", 4.0))
    )  # ZZZQ held only by FUNDA
    load_fund_holdings(
        conn, "FUNDB", write_holdings_csv(tmp_path, "fundb.csv", ("MSFT", "Microsoft", 6.0))
    )  # MSFT held by FUNDB too
    conn.execute(  # FUNDA also holds MSFT so MSFT is shared
        "INSERT INTO fund_holding (fund_symbol, holding_symbol, rank, weight, source)"
        " VALUES ('FUNDA', 'MSFT', 2, 1.0, 'holdings_file')"
    )
    forget_fund(conn, "FUNDA")
    # FUNDA and its exclusive stub are gone entirely...
    assert conn.execute("SELECT 1 FROM asset WHERE symbol='FUNDA'").fetchone() is None
    assert conn.execute("SELECT 1 FROM asset WHERE symbol='ZZZQ'").fetchone() is None
    assert conn.execute("SELECT 1 FROM company WHERE symbol='ZZZQ'").fetchone() is None
    # ...the shared stub survives because FUNDB still holds it.
    assert conn.execute("SELECT 1 FROM asset WHERE symbol='MSFT'").fetchone()


def test_forget_fund_does_not_crash_on_unrelated_dual_registered_symbol(tmp_path):
    """A dual-registered symbol elsewhere in the DB must not break an unrelated forget_fund.

    DUAL is a company stub that later gained a fund row (holdings were
    imported for it), so it carries asset_type='company' plus both a
    `company` row and a `fund` row, but no `fund_holding` row names it any
    more. It has nothing to do with the fund being forgotten. The GC sweeps
    at the end of `forget_fund` key only off `fund_holding.holding_symbol`,
    so they see DUAL as an orphaned company stub, delete its `company` row,
    then try to delete its `asset` row -- which `fund.symbol REFERENCES
    asset(symbol)` still needs, since DUAL's `fund` row survives. That raises
    sqlite3.IntegrityError and forget_fund crashes for ANY fund forgotten
    while such a row exists anywhere in the database.
    """
    conn = connect(tmp_path / "atlas.db")
    conn.execute("INSERT INTO asset (symbol, name, asset_type) VALUES ('DUAL', 'Dual Co', 'company')")
    conn.execute("INSERT INTO company (symbol) VALUES ('DUAL')")
    conn.execute("INSERT INTO fund (symbol, description) VALUES ('DUAL', '')")
    load_fund_holdings(
        conn, "FUNDC", write_holdings_csv(tmp_path, "fundc.csv", ("ZZZQ", "Exclusive Co", 4.0))
    )
    conn.commit()

    result = forget_fund(conn, "FUNDC")

    assert result.symbol == "FUNDC"
    # DUAL is untouched: unrelated to FUNDC, and still has a fund row.
    assert conn.execute("SELECT 1 FROM asset WHERE symbol='DUAL'").fetchone() is not None
    assert conn.execute("SELECT 1 FROM company WHERE symbol='DUAL'").fetchone() is not None
    assert conn.execute("SELECT 1 FROM fund WHERE symbol='DUAL'").fetchone() is not None
