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

SEED = Path("data/atlas_seed_universe.csv")
SCHWAB = Path("tests/fixtures/holdings_schwab.csv")
runner = CliRunner()


# --- db.database.forget_fund -------------------------------------------------


def test_forget_fund_removes_holding_and_score_rows_and_leaves_other_funds(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "SHCB", SCHWAB)
    conn.execute("INSERT INTO etf (symbol, description) VALUES ('OTHER', '')")
    score_all(conn)  # populates etf_score for both SHCB and OTHER

    result = forget_fund(conn, "SHCB")

    assert result.holdings_removed == 4  # AAPL, MSFT, AMZN, GOOG
    assert result.score_removed is True
    assert conn.execute("SELECT 1 FROM etf WHERE symbol = 'SHCB'").fetchone() is None
    assert conn.execute("SELECT 1 FROM etf_holding WHERE etf_symbol = 'SHCB'").fetchone() is None
    assert conn.execute("SELECT 1 FROM etf_score WHERE symbol = 'SHCB'").fetchone() is None
    # OTHER is untouched.
    assert conn.execute("SELECT 1 FROM etf WHERE symbol = 'OTHER'").fetchone() is not None
    assert conn.execute("SELECT 1 FROM etf_score WHERE symbol = 'OTHER'").fetchone() is not None


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
    assert conn.execute("SELECT 1 FROM etf WHERE symbol = 'SHCB'").fetchone() is None


def test_forget_fund_unknown_symbol_raises_atlas_data_error(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    with pytest.raises(AtlasDataError) as excinfo:
        forget_fund(conn, "NOPE")
    assert "NOPE" in str(excinfo.value)


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
        "SELECT COUNT(*) AS c FROM etf_holding WHERE etf_symbol = 'SHCB'"
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
    baseline = conn.execute("SELECT COUNT(*) AS c FROM etf").fetchone()["c"]

    runner.invoke(cli_app, ["import-holdings", "SHCB", str(SCHWAB), "--db", str(db_path)])
    conn = connect(db_path)
    after_phantom = conn.execute("SELECT COUNT(*) AS c FROM etf").fetchone()["c"]
    assert after_phantom == baseline + 1

    result = runner.invoke(cli_app, ["forget-fund", "SHCB", "--db", str(db_path)])
    assert result.exit_code == 0

    conn = connect(db_path)
    after_forget = conn.execute("SELECT COUNT(*) AS c FROM etf").fetchone()["c"]
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


def test_a_seed_fund_never_warns(tmp_path: Path) -> None:
    """A symbol that came from the seed universe is not a phantom."""
    db = tmp_path / "atlas.db"
    conn = connect(db)
    conn.execute(
        "INSERT INTO etf (symbol, description, source) VALUES ('SCHB', 'Schwab', 'Uploaded ETF Select List')"
    )
    conn.commit()
    conn.close()
    holdings = tmp_path / "h.csv"
    holdings.write_text("Ticker,Name,Weight\nAAA,Alpha,60.0\nBBB,Beta,35.0\n", encoding="utf-8")

    result = runner.invoke(cli_app, ["import-holdings", "SCHB", str(holdings), "--db", str(db)])

    assert result.exit_code == 0
    assert "not in the seed universe" not in result.output
