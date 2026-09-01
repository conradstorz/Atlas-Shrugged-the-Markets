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


def _add_weighted(conn, etf_symbol: str, holdings: list[tuple]) -> None:
    """holdings: (holding_symbol, weight_percent), stored as source='holdings_file'."""
    conn.execute(
        "INSERT INTO etf (symbol, description) VALUES (?, ?) ON CONFLICT(symbol) DO NOTHING",
        (etf_symbol, f"{etf_symbol} test fund"),
    )
    for rank, (holding, weight) in enumerate(holdings, start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, weight, source) "
            "VALUES (?, ?, ?, ?, 'holdings_file')",
            (etf_symbol, holding, rank, weight),
        )
    conn.commit()


def test_overlap_reports_each_side_holdings_basis(tmp_path: Path) -> None:
    """A comparison must disclose which kind of top ten each side used.

    An imported issuer top ten and a seed select-list top ten are different
    kinds of list; comparing one against the other is legitimate but must not
    look like a like-for-like comparison.
    """
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)  # AAA and BBB carry seed membership rows
    _add_weighted(conn, "WGT", [("X", 9.0), ("Y", 8.0)])

    mixed = compare_etfs(conn, "WGT", "AAA")
    assert mixed.left_source == "holdings_file"
    assert mixed.right_source == "seed_top_ten"
    assert mixed.mixed_basis is True

    same = compare_etfs(conn, "AAA", "BBB")
    assert same.left_source == "seed_top_ten"
    assert same.right_source == "seed_top_ten"
    assert same.mixed_basis is False


def test_overlap_basis_is_none_for_a_fund_with_no_holdings(tmp_path: Path) -> None:
    """An unknown or holdings-free fund reports no basis, and is not 'mixed'."""
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)

    result = compare_etfs(conn, "AAA", "NOPE")

    assert result.left_source == "seed_top_ten"
    assert result.right_source is None
    # One side having nothing to compare is an empty comparison, not a
    # mismatched-basis warning: there is no second basis to mismatch.
    assert result.mixed_basis is False
