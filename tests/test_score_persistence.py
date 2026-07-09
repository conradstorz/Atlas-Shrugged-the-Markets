"""Tests for reading persisted ETF scores without recomputing them."""

import sqlite3
from pathlib import Path

from atlas.db.database import connect
from atlas.scoring.engine import read_scores, score_all


def _seed_two_etfs(conn: sqlite3.Connection) -> None:
    conn.execute(
        "INSERT INTO etf (symbol, description, category) VALUES (?, ?, ?)",
        ("AAA", "Total broad market fund", "Large Blend"),
    )
    conn.execute(
        "INSERT INTO etf (symbol, description, category) VALUES (?, ?, ?)",
        ("BBB", "Treasury bond fund", "Fixed Income"),
    )
    conn.commit()


def test_read_scores_returns_persisted_rows_without_recomputing(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_two_etfs(conn)
    score_all(conn)

    # Overwrite a persisted score with a sentinel. read_scores must return the
    # stored value, proving it reads the table instead of re-scoring.
    conn.execute("UPDATE etf_score SET overall_score = 7 WHERE symbol = 'AAA'")
    conn.commit()

    scores = read_scores(conn)
    by_symbol = {s.symbol: s for s in scores}

    assert by_symbol["AAA"].overall_score == 7


def test_read_scores_is_sorted_by_overall_score_desc(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_two_etfs(conn)
    score_all(conn)
    conn.execute("UPDATE etf_score SET overall_score = 90 WHERE symbol = 'BBB'")
    conn.execute("UPDATE etf_score SET overall_score = 10 WHERE symbol = 'AAA'")
    conn.commit()

    scores = read_scores(conn)

    assert [s.symbol for s in scores] == ["BBB", "AAA"]


def test_read_scores_does_not_write_to_the_database(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_two_etfs(conn)
    score_all(conn)

    before = conn.execute("SELECT symbol, overall_score FROM etf_score ORDER BY symbol").fetchall()
    read_scores(conn)
    after = conn.execute("SELECT symbol, overall_score FROM etf_score ORDER BY symbol").fetchall()

    assert [tuple(r) for r in before] == [tuple(r) for r in after]
