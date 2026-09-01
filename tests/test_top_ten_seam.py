"""Tests for the top-ten seam: consumers that mean "top ten", not "all rows".

``etf_holding`` holds two very different kinds of row: seed select-list rows
(membership only, ``weight IS NULL``) and imported holdings-file rows (real
weights, and potentially hundreds of them per fund). Every consumer whose
output is *defined* as a top-ten — overlap, repeated holdings, the measured
diversification signal, the web fund page — must see exactly ten names: the
real top ten by weight when a holdings file has been imported, and the seed
select-list top ten otherwise.

The regression these tests exist to prevent is this branch's own defect class
in a new place: importing better data (real weights) producing a worse number —
a score or an overlap that moved only because a file was downloaded.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas.analytics.overlap import compare_etfs, top_repeated_holdings, top_ten_holdings
from atlas.db.database import connect, load_fund_holdings, load_seed_universe
from atlas.scoring.engine import _universe_holding_frequency, score_all

SEED = Path("data/atlas_seed_universe.csv")

# SCHB's seed select-list top ten, in seed order.
SCHB_SEED_TOP_TEN = [
    "NVDA",
    "AAPL",
    "MSFT",
    "AMZN",
    "GOOGL",
    "AVGO",
    "GOOG",
    "META",
    "TSLA",
    "MU",
]


def _write_holdings_csv(path: Path, rows: list[tuple[str, float]]) -> Path:
    """Write a minimal issuer-style holdings CSV (Ticker, Name, Weight)."""
    lines = ["Ticker,Name,Weight"]
    lines += [f"{symbol},{symbol} Inc,{weight}" for symbol, weight in rows]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _thirty_holdings(top_ten: list[str], tail_prefix: str) -> list[tuple[str, float]]:
    """Ten heavy names followed by twenty light tail names (sums to 80%)."""
    rows = [(symbol, 6.0) for symbol in top_ten]
    rows += [(f"{tail_prefix}{index:02d}", 1.0) for index in range(1, 21)]
    return rows


def _add_fund(conn: sqlite3.Connection, symbol: str) -> None:
    conn.execute("INSERT INTO etf (symbol, description) VALUES (?, ?)", (symbol, f"{symbol} test fund"))
    conn.commit()


def _add_seed_fund(conn: sqlite3.Connection, symbol: str, holdings: list[str]) -> None:
    """Insert a fund whose only holdings are unweighted seed select-list rows."""
    _add_fund(conn, symbol)
    for rank, holding in enumerate(holdings, start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source) "
            "VALUES (?, ?, ?, 'seed_top_ten')",
            (symbol, holding, rank),
        )
    conn.commit()


def test_top_ten_holdings_prefers_real_weights(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_fund(conn, "FUNDA")
    csv_path = _write_holdings_csv(
        tmp_path / "funda.csv", _thirty_holdings([f"H{i:02d}" for i in range(1, 11)], "T")
    )
    load_fund_holdings(conn, "FUNDA", csv_path)

    assert top_ten_holdings(conn, "FUNDA") == [f"H{i:02d}" for i in range(1, 11)]


def test_top_ten_holdings_falls_back_to_seed_rows(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_seed_fund(conn, "FUNDB", ["X", "Y", "Z"])

    assert top_ten_holdings(conn, "FUNDB") == ["X", "Y", "Z"]


def test_top_ten_holdings_returns_at_most_ten_in_both_modes(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_seed_fund(conn, "SEEDY", [f"S{i:02d}" for i in range(1, 13)])
    _add_fund(conn, "WEIGHTY")
    load_fund_holdings(
        conn,
        "WEIGHTY",
        _write_holdings_csv(
            tmp_path / "w.csv", _thirty_holdings([f"H{i:02d}" for i in range(1, 11)], "T")
        ),
    )

    assert len(top_ten_holdings(conn, "SEEDY")) == 10
    assert len(top_ten_holdings(conn, "WEIGHTY")) == 10


def test_top_ten_holdings_is_case_insensitive(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_seed_fund(conn, "FUNDB", ["X", "Y"])

    assert top_ten_holdings(conn, "fundb") == ["X", "Y"]


def test_top_ten_holdings_of_unknown_fund_is_empty(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")

    assert top_ten_holdings(conn, "NOPE") == []


def test_weighted_fund_contributes_only_its_top_ten_to_repeat_holdings(tmp_path: Path) -> None:
    """A 30-row import must not inflate a fund's contribution 30x."""
    conn = connect(tmp_path / "atlas.db")
    _add_fund(conn, "FUNDA")
    load_fund_holdings(
        conn,
        "FUNDA",
        _write_holdings_csv(
            tmp_path / "a.csv", _thirty_holdings([f"H{i:02d}" for i in range(1, 11)], "T")
        ),
    )
    # FUNDB shares one of FUNDA's top-ten names (H01) and one tail name (T05).
    _add_seed_fund(conn, "FUNDB", ["H01", "T05"])

    counts = {row["holding_symbol"]: row["etf_count"] for row in top_repeated_holdings(conn)}

    # H01 is in both funds' top tens. T05 is only in FUNDA's *tail*, so it is
    # held by exactly one top ten and must not appear as repeated at all.
    assert counts == {"H01": 2}


def test_weighted_fund_contributes_only_its_top_ten_to_universe_frequency(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_fund(conn, "FUNDA")
    load_fund_holdings(
        conn,
        "FUNDA",
        _write_holdings_csv(
            tmp_path / "a.csv", _thirty_holdings([f"H{i:02d}" for i in range(1, 11)], "T")
        ),
    )

    freq = _universe_holding_frequency(conn)

    assert set(freq) == {f"H{i:02d}" for i in range(1, 11)}


def test_compare_overlap_uses_real_top_tens_not_full_holdings(tmp_path: Path) -> None:
    """Identical top tens, different tails, must still read as full overlap."""
    conn = connect(tmp_path / "atlas.db")
    for symbol in ("FUNDA", "FUNDB"):
        _add_fund(conn, symbol)
    shared_top_ten = [f"H{i:02d}" for i in range(1, 11)]
    load_fund_holdings(
        conn, "FUNDA", _write_holdings_csv(tmp_path / "a.csv", _thirty_holdings(shared_top_ten, "TA"))
    )
    load_fund_holdings(
        conn, "FUNDB", _write_holdings_csv(tmp_path / "b.csv", _thirty_holdings(shared_top_ten, "TB"))
    )

    result = compare_etfs(conn, "FUNDA", "FUNDB")

    assert result.left_count == 10
    assert result.right_count == 10
    assert result.shared_count == 10
    assert result.jaccard_percent == 100.0


def test_score_does_not_change_merely_because_holdings_were_imported(tmp_path: Path) -> None:
    """THE regression test for the Critical.

    A fund whose imported top ten by weight equals its seed top ten must score
    exactly as it did before the import. Better data must not move a number the
    better data does not actually change.
    """
    before_conn = connect(tmp_path / "before.db")
    load_seed_universe(before_conn, SEED)
    before = {score.symbol: score for score in score_all(before_conn)}

    after_conn = connect(tmp_path / "after.db")
    load_seed_universe(after_conn, SEED)
    load_fund_holdings(
        after_conn,
        "SCHB",
        _write_holdings_csv(tmp_path / "schb.csv", _thirty_holdings(SCHB_SEED_TOP_TEN, "T")),
    )
    after = {score.symbol: score for score in score_all(after_conn)}

    assert after["SCHB"].diversification_score == before["SCHB"].diversification_score
    assert after["SCHB"].overall_score == before["SCHB"].overall_score
    # No other fund's score may move either: SCHB's tail must not enter the
    # universe-wide holding frequency that every other score depends on.
    assert {symbol: score.overall_score for symbol, score in after.items()} == {
        symbol: score.overall_score for symbol, score in before.items()
    }


def test_compare_overlap_unchanged_by_an_import_matching_the_seed_top_ten(tmp_path: Path) -> None:
    """``compare-overlap SCHB ITOT`` must not invert when SCHB gains real weights."""
    before_conn = connect(tmp_path / "before.db")
    load_seed_universe(before_conn, SEED)
    before = compare_etfs(before_conn, "SCHB", "ITOT")

    after_conn = connect(tmp_path / "after.db")
    load_seed_universe(after_conn, SEED)
    load_fund_holdings(
        after_conn,
        "SCHB",
        _write_holdings_csv(tmp_path / "schb.csv", _thirty_holdings(SCHB_SEED_TOP_TEN, "T")),
    )
    after = compare_etfs(after_conn, "SCHB", "ITOT")

    assert after.jaccard_percent == before.jaccard_percent
    assert after.shared_symbols == before.shared_symbols
