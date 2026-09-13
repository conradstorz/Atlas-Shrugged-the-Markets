"""Tests for issue #7: undoing a typo'd `import-holdings` symbol.

`load_fund_holdings` deliberately creates a minimal `etf` row when the given
symbol is not already in the universe, so holdings can be imported for a fund
outside the seed select-list. The failure mode that motivates this file is a
typo — `import-holdings SHCB ...` instead of `SCHB` — which used to create a
permanent phantom fund with no way to remove it short of deleting the
database.

The fix is: warn (but still import) at the CLI when the symbol is new, and add
`atlas forget-fund SYMBOL` to remove a fund and everything Atlas derived from
it. `forget-fund` must never touch `portfolio_position`, since those rows are
the investor's actual holdings and are not derived from the universe at all.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from atlas.cli.main import app as cli_app
from atlas.db.database import connect, forget_fund, load_fund_holdings
from atlas.exceptions import AtlasDataError
from atlas.scoring.engine import score_all
from db_fixtures import add_fund

SEED = Path("data/atlas_seed_universe.csv")
SCHWAB = Path("tests/fixtures/holdings_schwab.csv")
runner = CliRunner()


def write_holdings_csv_for(tmp_path: Path, name: str, *rows: tuple[str, str, float]) -> Path:
    """(ticker, holding_name, weight_percent) rows in an issuer-file shape."""
    path = tmp_path / name
    lines = ["Ticker,Name,Weight\n"]
    lines += [f"{ticker},{holding_name},{weight}\n" for ticker, holding_name, weight in rows]
    path.write_text("".join(lines), encoding="utf-8")
    return path


# --- db.database.forget_fund -------------------------------------------------


def test_forget_fund_removes_holding_and_score_rows_and_leaves_other_funds(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "SHCB", SCHWAB)
    add_fund(conn, "OTHER")
    score_all(conn)  # populates fund_score for both SHCB and OTHER

    result = forget_fund(conn, "SHCB")

    assert result.holdings_removed == 4  # AAPL, MSFT, AMZN, GOOG
    assert result.score_removed is True
    assert conn.execute("SELECT 1 FROM fund WHERE symbol = 'SHCB'").fetchone() is None
    assert conn.execute("SELECT 1 FROM fund_holding WHERE fund_symbol = 'SHCB'").fetchone() is None
    assert conn.execute("SELECT 1 FROM fund_score WHERE symbol = 'SHCB'").fetchone() is None
    # OTHER is untouched.
    assert conn.execute("SELECT 1 FROM fund WHERE symbol = 'OTHER'").fetchone() is not None
    assert conn.execute("SELECT 1 FROM fund_score WHERE symbol = 'OTHER'").fetchone() is not None


def test_forget_fund_leaves_portfolio_position_intact(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "SHCB", SCHWAB)
    conn.execute("INSERT INTO portfolio (name) VALUES ('Primary')")
    portfolio_id = conn.execute("SELECT id FROM portfolio WHERE name = 'Primary'").fetchone()["id"]
    conn.execute(
        "INSERT INTO portfolio_position (portfolio_id, symbol, market_value) VALUES (?, 'SHCB', 50000)",
        (portfolio_id,),
    )
    conn.commit()

    result = forget_fund(conn, "SHCB")

    assert result.portfolio_positions == 1
    position = conn.execute(
        "SELECT symbol, market_value FROM portfolio_position WHERE symbol = 'SHCB'"
    ).fetchone()
    assert position is not None
    assert position["market_value"] == 50000
    # The fund itself is still gone.
    assert conn.execute("SELECT 1 FROM fund WHERE symbol = 'SHCB'").fetchone() is None


def test_forget_fund_unknown_symbol_raises_atlas_data_error(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    with pytest.raises(AtlasDataError) as excinfo:
        forget_fund(conn, "NOPE")
    assert "NOPE" in str(excinfo.value)


def test_forget_fund_dual_registered_symbol_with_nothing_else_holding_it(tmp_path: Path) -> None:
    """A symbol can be dual-registered: a company stub that later gained a fund row.

    This happens when some fund's holdings named the symbol first (creating an
    `asset` row with `asset_type='company'` and a `company` row), and holdings
    were later imported for that same symbol (creating a `fund` row for it,
    without ever changing `asset_type`). `company.symbol` references
    `asset(symbol)`, so deleting the `asset` row without first deleting the
    `company` row raises `sqlite3.IntegrityError`. When nothing else holds the
    symbol, the asset row is going away, so the company row must go with it.
    """
    conn = connect(tmp_path / "atlas.db")
    conn.execute("INSERT INTO asset (symbol, name, asset_type) VALUES ('DUAL', 'Dual Co', 'company')")
    conn.execute("INSERT INTO company (symbol) VALUES ('DUAL')")
    conn.execute("INSERT INTO fund (symbol, description) VALUES ('DUAL', '')")
    conn.commit()

    result = forget_fund(conn, "DUAL")

    assert result.symbol == "DUAL"
    assert conn.execute("SELECT 1 FROM asset WHERE symbol = 'DUAL'").fetchone() is None
    assert conn.execute("SELECT 1 FROM company WHERE symbol = 'DUAL'").fetchone() is None
    assert conn.execute("SELECT 1 FROM fund WHERE symbol = 'DUAL'").fetchone() is None


def test_forget_fund_gcs_a_fund_typed_asset_left_with_no_subtype_row(tmp_path: Path) -> None:
    """A fund-holding-a-fund case must not leak a bare `asset` row forever.

    TARGETX is itself a fund (holdings were imported for it) and is also held
    by FUNDX. Forgetting TARGETX first rightly leaves its `asset` row behind
    (FUNDX's `fund_holding` row still references it) with `asset_type='fund'`,
    no `fund` row, and no `company` row -- an asset with no subtype at all.
    Forgetting FUNDX next removes the only remaining reference to TARGETX, so
    that leftover `asset` row has nothing anchoring it any more. The GC sweeps
    in `forget_fund` keyed only off `asset_type = 'company'` never touch it,
    leaking it permanently.
    """
    conn = connect(tmp_path / "atlas.db")
    targetx_csv = tmp_path / "targetx.csv"
    targetx_csv.write_text("Ticker,Name,Weight\nZZZQ,Exclusive Co,4.0\n", encoding="utf-8")
    load_fund_holdings(conn, "TARGETX", targetx_csv)

    fundx_csv = tmp_path / "fundx.csv"
    fundx_csv.write_text("Ticker,Name,Weight\nTARGETX,Target Fund,10.0\n", encoding="utf-8")
    load_fund_holdings(conn, "FUNDX", fundx_csv)
    conn.commit()

    # Sanity: TARGETX is a real fund, held by FUNDX.
    assert conn.execute("SELECT asset_type FROM asset WHERE symbol = 'TARGETX'").fetchone()[0] == "fund"
    assert conn.execute(
        "SELECT 1 FROM fund_holding WHERE fund_symbol = 'FUNDX' AND holding_symbol = 'TARGETX'"
    ).fetchone()

    forget_fund(conn, "TARGETX")

    # TARGETX's asset row survives -- FUNDX's fund_holding row still needs it --
    # but with no subtype row of its own any more.
    row = conn.execute("SELECT asset_type FROM asset WHERE symbol = 'TARGETX'").fetchone()
    assert row is not None
    assert row["asset_type"] == "fund"
    assert conn.execute("SELECT 1 FROM fund WHERE symbol = 'TARGETX'").fetchone() is None
    assert conn.execute("SELECT 1 FROM company WHERE symbol = 'TARGETX'").fetchone() is None

    forget_fund(conn, "FUNDX")

    # Nothing references TARGETX any more; its orphaned asset row must be gone.
    assert conn.execute("SELECT 1 FROM asset WHERE symbol = 'TARGETX'").fetchone() is None


def test_forget_fund_dual_registered_symbol_still_held_by_another_fund(tmp_path: Path) -> None:
    """Same dual-registered state, but another fund still holds the symbol.

    The asset row must survive (the surviving `fund_holding` row still
    references it), and the company row must survive with it — it anchors the
    subtype invariant for the holding that remains. Only the `fund` row for
    the forgotten symbol itself should go.
    """
    conn = connect(tmp_path / "atlas.db")
    conn.execute("INSERT INTO asset (symbol, name, asset_type) VALUES ('DUAL', 'Dual Co', 'company')")
    conn.execute("INSERT INTO company (symbol) VALUES ('DUAL')")
    conn.execute("INSERT INTO fund (symbol, description) VALUES ('DUAL', '')")
    conn.execute("INSERT INTO asset (symbol, name, asset_type) VALUES ('OTHER', 'Other Fund', 'fund')")
    conn.execute("INSERT INTO fund (symbol, description) VALUES ('OTHER', '')")
    conn.execute(
        "INSERT INTO fund_holding (fund_symbol, holding_symbol, rank, source) "
        "VALUES ('OTHER', 'DUAL', 1, 'seed_top_ten')"
    )
    conn.commit()

    result = forget_fund(conn, "DUAL")

    assert result.symbol == "DUAL"
    assert conn.execute("SELECT 1 FROM asset WHERE symbol = 'DUAL'").fetchone() is not None
    assert conn.execute("SELECT 1 FROM company WHERE symbol = 'DUAL'").fetchone() is not None
    assert conn.execute("SELECT 1 FROM fund WHERE symbol = 'DUAL'").fetchone() is None


# --- CLI: warning on import-holdings for an unfamiliar symbol ---------------


def test_import_holdings_known_symbol_prints_no_warning(tmp_path: Path) -> None:
    db_path = tmp_path / "atlas.db"
    runner.invoke(cli_app, ["import-seed", "--seed", str(SEED), "--db", str(db_path)])

    result = runner.invoke(cli_app, ["import-holdings", "SCHB", str(SCHWAB), "--db", str(db_path)])
    output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "Warning" not in output
    assert "not in the seed universe" not in output


def test_import_holdings_unknown_symbol_prints_warning_and_still_imports(tmp_path: Path) -> None:
    db_path = tmp_path / "atlas.db"
    runner.invoke(cli_app, ["import-seed", "--seed", str(SEED), "--db", str(db_path)])

    result = runner.invoke(cli_app, ["import-holdings", "SHCB", str(SCHWAB), "--db", str(db_path)])
    output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "Warning: SHCB is not in the seed universe." in output
    assert "forget-fund SHCB" in output
    # The import still happened despite the warning.
    assert "Imported 4 holdings for SHCB" in output

    conn = connect(db_path)
    rows = conn.execute(
        "SELECT COUNT(*) AS c FROM fund_holding WHERE fund_symbol = 'SHCB'"
    ).fetchone()["c"]
    assert rows == 4


# --- CLI: forget-fund ---------------------------------------------------------


def test_forget_fund_command_reports_what_it_removed(tmp_path: Path) -> None:
    db_path = tmp_path / "atlas.db"
    runner.invoke(cli_app, ["import-seed", "--seed", str(SEED), "--db", str(db_path)])
    runner.invoke(cli_app, ["import-holdings", "SHCB", str(SCHWAB), "--db", str(db_path)])

    result = runner.invoke(cli_app, ["forget-fund", "SHCB", "--db", str(db_path)])
    output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "Removed SHCB: 4 holdings, 0 score, 1 universe entry." in output


def test_forget_fund_command_reports_surviving_portfolio_position(tmp_path: Path) -> None:
    db_path = tmp_path / "atlas.db"
    runner.invoke(cli_app, ["import-seed", "--seed", str(SEED), "--db", str(db_path)])
    runner.invoke(cli_app, ["import-holdings", "SHCB", str(SCHWAB), "--db", str(db_path)])

    conn = connect(db_path)
    conn.execute("INSERT INTO portfolio (name) VALUES ('Primary')")
    portfolio_id = conn.execute("SELECT id FROM portfolio WHERE name = 'Primary'").fetchone()["id"]
    conn.execute(
        "INSERT INTO portfolio_position (portfolio_id, symbol, market_value) VALUES (?, 'SHCB', 50000)",
        (portfolio_id,),
    )
    conn.commit()

    result = runner.invoke(cli_app, ["forget-fund", "SHCB", "--db", str(db_path)])
    output = " ".join(result.output.split())

    assert result.exit_code == 0
    assert "SHCB" in output
    assert "position" in output.lower()

    conn = connect(db_path)
    position = conn.execute("SELECT 1 FROM portfolio_position WHERE symbol = 'SHCB'").fetchone()
    assert position is not None


def test_forget_fund_command_unknown_symbol_exits_nonzero(tmp_path: Path) -> None:
    db_path = tmp_path / "atlas.db"
    runner.invoke(cli_app, ["import-seed", "--seed", str(SEED), "--db", str(db_path)])

    result = runner.invoke(cli_app, ["forget-fund", "NOPE", "--db", str(db_path)])
    output = " ".join(result.output.split())

    assert result.exit_code == 1
    assert "NOPE" in output
    assert "Traceback" not in output


# --- Round trip: phantom import raises the universe count, forget restores it -


def test_round_trip_phantom_import_and_forget_restores_universe_count(tmp_path: Path) -> None:
    db_path = tmp_path / "atlas.db"
    runner.invoke(cli_app, ["import-seed", "--seed", str(SEED), "--db", str(db_path)])

    conn = connect(db_path)
    baseline = conn.execute("SELECT COUNT(*) AS c FROM fund").fetchone()["c"]

    runner.invoke(cli_app, ["import-holdings", "SHCB", str(SCHWAB), "--db", str(db_path)])
    conn = connect(db_path)
    after_phantom = conn.execute("SELECT COUNT(*) AS c FROM fund").fetchone()["c"]
    assert after_phantom == baseline + 1

    result = runner.invoke(cli_app, ["forget-fund", "SHCB", "--db", str(db_path)])
    assert result.exit_code == 0

    conn = connect(db_path)
    after_forget = conn.execute("SELECT COUNT(*) AS c FROM fund").fetchone()["c"]
    assert after_forget == baseline


def test_the_warning_repeats_on_every_import_for_a_phantom_fund(tmp_path: Path) -> None:
    """A phantom must not go quiet after its first import.

    `load_fund_holdings` creates a bare `etf` row for an unknown symbol, so a
    check for mere existence would warn once and then stay silent, letting the
    phantom fade into the universe. Seed-derived rows carry a `source`; a
    phantom's is NULL.
    """
    holdings = tmp_path / "h.csv"
    holdings.write_text("Ticker,Name,Weight\nAAA,Alpha,60.0\nBBB,Beta,35.0\n", encoding="utf-8")
    db = tmp_path / "atlas.db"

    for attempt in ("first", "second"):
        result = runner.invoke(cli_app, ["import-holdings", "SHCB", str(holdings), "--db", str(db)])
        assert result.exit_code == 0, attempt
        assert "not in the seed universe" in result.output, f"no warning on the {attempt} import"


def test_import_holdings_for_company_symbol_does_not_print_phantom_warning(tmp_path: Path) -> None:
    """A company-typed symbol gets the refusal, not a contradictory phantom warning.

    NVDA is a company stub (some other fund's holdings named it). Importing
    holdings *for* NVDA is refused by `load_fund_holdings` -- it is a company,
    not a fund -- but the CLI's "unfamiliar symbol" check ran first and looked
    only at whether NVDA had a seed-derived `fund` row, which it never did,
    so it printed "Importing anyway and creating the fund" immediately before
    the refusal said no fund would be created. The warning must not fire for a
    symbol the refusal is about to reject.
    """
    db_path = tmp_path / "atlas.db"
    conn = connect(db_path)
    load_fund_holdings(
        conn, "SOMEFUND",
        write_holdings_csv_for(tmp_path, "somefund.csv", ("NVDA", "NVIDIA Corp", 7.5)),
    )  # NVDA -> company stub
    conn.close()

    result = runner.invoke(
        cli_app,
        ["import-holdings", "NVDA", str(write_holdings_csv_for(tmp_path, "nvda.csv", ("AAPL", "Apple Inc", 3.0))),
         "--db", str(db_path)],
    )
    output = " ".join(result.output.split())

    assert result.exit_code != 0
    assert "Importing anyway and creating the fund" not in output
    assert "Warning" not in output
    assert "NVDA is registered as a company" in output
    assert "Not importing a holdings file for it." in output


def test_a_seed_fund_never_warns(tmp_path: Path) -> None:
    """A symbol that came from the seed universe is not a phantom."""
    db = tmp_path / "atlas.db"
    conn = connect(db)
    add_fund(conn, "SCHB", "Schwab", source="Uploaded ETF Select List")
    conn.commit()
    conn.close()
    holdings = tmp_path / "h.csv"
    holdings.write_text("Ticker,Name,Weight\nAAA,Alpha,60.0\nBBB,Beta,35.0\n", encoding="utf-8")

    result = runner.invoke(cli_app, ["import-holdings", "SCHB", str(holdings), "--db", str(db)])

    assert result.exit_code == 0
    assert "not in the seed universe" not in result.output
