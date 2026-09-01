"""Tests for how the CLI reports a bad data file to the investor.

A holdings file whose weights are fractions rather than percent is the most
dangerous realistic failure mode: silently accepted, it would understate every
look-through figure by a factor of a hundred. The guard already refuses it; what
these tests pin down is that the refusal reads as a clean, actionable error and
exits non-zero, rather than dumping a Rich traceback with a local-variable table.
"""

from __future__ import annotations

from pathlib import Path

from typer.testing import CliRunner

from atlas.cli.main import app

FRACTIONS = Path("tests/fixtures/holdings_fractions.csv")
runner = CliRunner()


def test_import_holdings_reports_a_fractions_file_cleanly(tmp_path: Path) -> None:
    result = runner.invoke(
        app,
        ["import-holdings", "XYZ", str(FRACTIONS), "--db", str(tmp_path / "atlas.db")],
    )

    # Rich hard-wraps console output, so compare on a whitespace-normalized copy.
    output = " ".join(result.output.split())

    assert result.exit_code == 1
    assert "looks like fractions" in output
    assert "Convert weights to percent (e.g. 6.83) before importing." in output
    assert "Traceback" not in output
    assert "AtlasDataError" not in output
    # A traceback would name the module the exception was raised from.
    assert "holdings_file.py" not in output


def test_import_holdings_leaves_no_holdings_behind_after_a_rejected_file(tmp_path: Path) -> None:
    db_path = tmp_path / "atlas.db"
    runner.invoke(app, ["import-holdings", "XYZ", str(FRACTIONS), "--db", str(db_path)])

    from atlas.db.database import connect

    conn = connect(db_path)
    rows = conn.execute("SELECT COUNT(*) AS count FROM etf_holding").fetchone()["count"]
    assert rows == 0
