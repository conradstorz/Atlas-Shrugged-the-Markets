from pathlib import Path

from atlas.db.database import connect, load_portfolio_csv, load_seed_universe
from atlas.journal.service import add_journal_entry, list_journal_entries
from atlas.reports.markdown import build_research_report


def test_report_contains_scoreboard(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    report = build_research_report(conn)
    assert "# Atlas Research Report" in report
    assert "## ETF Scoreboard" in report
    assert "## Most Repeated Seed Holdings" in report


def test_journal_round_trip(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    entry_id = add_journal_entry(
        conn,
        symbol="SCHB",
        decision="watch",
        thesis="Core U.S. broad market exposure.",
        confidence=90,
        max_allocation_percent=50,
        change_mind_conditions="Expense ratio or index methodology changes.",
    )
    entries = list_journal_entries(conn, symbol="SCHB")
    assert entries[0].id == entry_id
    assert entries[0].symbol == "SCHB"
    assert entries[0].confidence == 90


def test_report_can_include_private_portfolio(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    load_portfolio_csv(conn, "Primary", Path("examples/sample_portfolio.csv"))
    report = build_research_report(conn, portfolio_name="Primary")
    assert "## Portfolio: Primary" in report
    assert "Combined Concentration" in report
    assert "not looked through" in report
