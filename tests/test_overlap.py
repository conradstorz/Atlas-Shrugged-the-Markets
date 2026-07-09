"""Tests for analytics.overlap with hand-computed expected values.

These use a small, controlled ETF universe inserted directly (not the seed CSV)
so every Jaccard/count assertion can be verified by hand.
"""

from pathlib import Path

from atlas.analytics.overlap import compare_etfs, top_repeated_holdings
from atlas.db.database import connect


def _seed_universe(conn) -> None:
    """AAA holds {X, Y}; BBB holds {X, Z}; CCC holds {Q}."""
    for symbol in ("AAA", "BBB", "CCC"):
        conn.execute(
            "INSERT INTO etf (symbol, description) VALUES (?, ?)",
            (symbol, f"{symbol} test fund"),
        )
    holdings = {
        "AAA": ["X", "Y"],
        "BBB": ["X", "Z"],
        "CCC": ["Q"],
    }
    for etf_symbol, symbols in holdings.items():
        for rank, holding in enumerate(symbols, start=1):
            conn.execute(
                "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank) VALUES (?, ?, ?)",
                (etf_symbol, holding, rank),
            )
    conn.commit()


def test_overlap_jaccard_is_intersection_over_union(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)

    result = compare_etfs(conn, "AAA", "BBB")

    # shared {X}=1, union {X,Y,Z}=3 -> 1/3 = 33.3%
    assert result.shared_count == 1
    assert result.left_count == 2
    assert result.right_count == 2
    assert result.shared_symbols == ["X"]
    assert result.jaccard_percent == 33.3


def test_overlap_is_case_insensitive(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)

    result = compare_etfs(conn, "aaa", "bbb")

    assert result.left_symbol == "AAA"
    assert result.right_symbol == "BBB"
    assert result.shared_symbols == ["X"]


def test_overlap_of_disjoint_etfs_is_zero(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)

    result = compare_etfs(conn, "AAA", "CCC")

    assert result.shared_count == 0
    assert result.jaccard_percent == 0.0
    assert result.shared_symbols == []


def test_overlap_with_unknown_etf_does_not_divide_by_zero(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)

    result = compare_etfs(conn, "AAA", "NOPE")

    assert result.right_count == 0
    assert result.shared_count == 0
    assert result.jaccard_percent == 0.0


def test_repeated_holdings_only_returns_holdings_in_more_than_one_etf(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)

    rows = top_repeated_holdings(conn)

    # X is in AAA and BBB (count 2); Y, Z, Q appear once and are filtered out.
    assert len(rows) == 1
    assert rows[0]["holding_symbol"] == "X"
    assert rows[0]["etf_count"] == 2
    assert set(rows[0]["etfs"].split(", ")) == {"AAA", "BBB"}
