from pathlib import Path

from atlas.analytics.overlap import compare_etfs, top_repeated_holdings
from atlas.db.database import connect, load_portfolio_csv, load_seed_universe
from atlas.portfolio.analysis import portfolio_hidden_concentration, summarize_portfolio
from atlas.scoring.engine import score_all


def test_seed_universe_scores(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    loaded = load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    scores = score_all(conn)
    assert loaded > 0
    assert scores
    assert all(0 <= score.overall_score <= 100 for score in scores)


def test_top_ten_overlap(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    result = compare_etfs(conn, "SCHB", "SCHG")
    assert result.left_count > 0
    assert result.right_count > 0
    assert result.shared_count > 0
    assert result.jaccard_percent > 0


def test_repeated_holdings(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    rows = top_repeated_holdings(conn)
    assert rows
    assert rows[0]["etf_count"] > 1


def test_portfolio_import_and_concentration(tmp_path: Path) -> None:
    portfolio_csv = tmp_path / "portfolio.csv"
    portfolio_csv.write_text(
        "Symbol,Description,Asset Type,Market Value,Notes\n"
        "SCHB,Schwab U.S. Broad Market ETF,ETF,50000,Core\n"
        "SCHD,Schwab U.S. Dividend Equity ETF,ETF,25000,Dividend\n"
        "RSP,Invesco S&P 500 Equal Weight ETF,ETF,15000,Equal weight\n",
        encoding="utf-8",
    )
    conn = connect(tmp_path / "atlas.db")
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    loaded = load_portfolio_csv(conn, "Primary", portfolio_csv)
    summary = summarize_portfolio(conn, "Primary")
    concentration = portfolio_hidden_concentration(conn, "Primary")
    assert loaded == 3
    assert summary.position_count == 3
    assert summary.total_value == 90000
    assert concentration
