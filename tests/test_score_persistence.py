"""Tests for reading persisted ETF scores without recomputing them."""

import sqlite3
from pathlib import Path

from atlas.db.database import connect
from atlas.scoring.engine import read_scores, score_all


def _seed_two_etfs(conn: sqlite3.Connection) -> None:
    """Two funds that both really score, so persistence is exercised on numbers.

    Each carries a gross expense ratio, without which `score_all` would store a
    NULL `overall_score` for both and these tests would only ever round-trip
    the sentinel values they write by hand.
    """
    conn.execute(
        "INSERT INTO etf (symbol, description, category, gross_expense_ratio) "
        "VALUES (?, ?, ?, ?)",
        ("AAA", "Total broad market fund", "Large Blend", "0.03%"),
    )
    conn.execute(
        "INSERT INTO etf (symbol, description, category, gross_expense_ratio) "
        "VALUES (?, ?, ?, ?)",
        ("BBB", "Treasury bond fund", "Fixed Income", "0.05%"),
    )
    conn.commit()


def _seed_an_unscorable_etf(conn: sqlite3.Connection) -> None:
    """A fund with nothing measurable: `score_all` stores a NULL overall score."""
    conn.execute(
        "INSERT INTO etf (symbol, description, category) VALUES (?, ?, ?)",
        ("ZZZ", "Total broad market fund", "Large Blend"),
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


def test_persisted_scores_are_real_numbers_before_any_test_overwrites_them(
    tmp_path: Path,
) -> None:
    """Guard on the fixture itself, so the tests above cannot go hollow.

    If `_seed_two_etfs` ever stopped producing scorable funds, every test in
    this module would still pass while round-tripping only its own sentinels.

    AAA is Foundation (AI 8) with a 0.03% ratio (cost 10): 18 * (80 / 20) + 20
    = 92. BBB is Defensive (AI 1) with a 0.05% ratio (cost 10): 11 * 4 + 20 = 64.
    Neither has IT exposure or a holdings file, so both score on two components.
    """
    conn = connect(tmp_path / "atlas.db")
    _seed_two_etfs(conn)
    score_all(conn)

    stored = conn.execute("SELECT overall_score FROM etf_score ORDER BY symbol").fetchall()

    assert [row["overall_score"] for row in stored] == [92, 64]


def test_read_scores_puts_an_unscored_fund_last(tmp_path: Path) -> None:
    """The NULL-ordering path of `read_scores`, on scores it computed itself."""
    conn = connect(tmp_path / "atlas.db")
    _seed_two_etfs(conn)
    _seed_an_unscorable_etf(conn)
    score_all(conn)

    scores = read_scores(conn)

    assert scores[-1].symbol == "ZZZ"
    assert scores[-1].overall_score is None
    assert [s.symbol for s in scores[:-1]] == ["AAA", "BBB"]
