from pathlib import Path

from atlas.db.database import connect, load_fund_holdings, load_portfolio_csv, load_seed_universe
from atlas.journal.service import add_journal_entry, list_journal_entries
from atlas.reports.markdown import build_research_report

SCHWAB_HOLDINGS = Path("tests/fixtures/holdings_schwab.csv")


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
    assert "### Coverage" in report


def test_report_coverage_section_has_per_fund_lines(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    load_portfolio_csv(conn, "Primary", Path("examples/sample_portfolio.csv"))
    report = build_research_report(conn, portfolio_name="Primary")
    coverage_section = report.split("### Coverage", 1)[1]
    # Every fund position in the sample portfolio should appear in the
    # per-fund coverage table.
    assert "SCHB" in coverage_section
    assert "SCHD" in coverage_section
    assert "RSP" in coverage_section
    assert "SGOV" in coverage_section


def test_report_concentration_preamble_drops_stale_prototype_language(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    load_portfolio_csv(conn, "Primary", Path("examples/sample_portfolio.csv"))
    report = build_research_report(conn, portfolio_name="Primary")
    assert "equal-weight" not in report
    assert "prototype estimate" not in report
    assert "Full holdings are not yet imported." not in report
    assert "Top-ten holdings do not include actual holding weights in the seed file." not in report


def test_report_shows_modeled_percent_for_weighted_fund(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    load_portfolio_csv(conn, "Primary", Path("examples/sample_portfolio.csv"))
    load_fund_holdings(conn, "SCHB", SCHWAB_HOLDINGS)
    report = build_research_report(conn, portfolio_name="Primary")
    coverage_section = report.split("### Coverage", 1)[1].split("### Combined Concentration", 1)[0]
    assert "19.08%" in coverage_section  # SCHB's imported weight sum, applied to its $50,000 position
