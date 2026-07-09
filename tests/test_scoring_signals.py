"""Tests that ETF scores are grounded in real DB data, not fabricated constants.

Diversification is derived from measured holdings overlap; resilience is eroded
by the real parsed information-technology exposure.
"""

import sqlite3
from pathlib import Path

from atlas.db.database import connect
from atlas.scoring.engine import measured_diversification, score_all


# --- measured_diversification (pure function) --------------------------------

def test_all_unique_holdings_score_max_diversification() -> None:
    freq = {"X": 1, "Y": 1}
    assert measured_diversification(["X", "Y"], freq) == 10


def test_all_shared_holdings_score_min_diversification() -> None:
    freq = {"X": 5, "Y": 3}
    assert measured_diversification(["X", "Y"], freq) == 0


def test_half_shared_holdings_score_middle() -> None:
    freq = {"X": 2, "Y": 1}
    assert measured_diversification(["X", "Y"], freq) == 5


def test_no_holdings_returns_none() -> None:
    assert measured_diversification([], {}) is None


# --- integration through score_all -------------------------------------------

def _add_etf(conn: sqlite3.Connection, symbol: str, description: str,
             holdings: list[str], it_exposure: str = "") -> None:
    conn.execute(
        "INSERT INTO etf (symbol, description, category, information_technology_exposure) "
        "VALUES (?, ?, ?, ?)",
        (symbol, description, "", it_exposure),
    )
    for rank, holding in enumerate(holdings, start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank) VALUES (?, ?, ?)",
            (symbol, holding, rank),
        )
    conn.commit()


def test_unique_holdings_score_higher_diversification_than_crowded(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # X and Y are crowded (also held by E1/E2); P and Q are unique to UNIQ.
    _add_etf(conn, "UNIQ", "Some fund", ["P", "Q"])
    _add_etf(conn, "CROWD", "Some fund", ["X", "Y"])
    _add_etf(conn, "E1", "Some fund", ["X"])
    _add_etf(conn, "E2", "Some fund", ["Y"])

    by_symbol = {s.symbol: s for s in score_all(conn)}

    assert by_symbol["UNIQ"].diversification_score == 10
    assert by_symbol["CROWD"].diversification_score == 0
    assert by_symbol["UNIQ"].diversification_score > by_symbol["CROWD"].diversification_score


def test_resilience_erodes_with_real_it_exposure(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "LOWIT", "Total broad market", [], it_exposure="10%")
    _add_etf(conn, "HIGHIT", "Total broad market", [], it_exposure="50%")

    by_symbol = {s.symbol: s for s in score_all(conn)}

    # Same role (Foundation, baseline resilience 7). IT 50% -> 7 - (50-20)/10 = 4.
    assert by_symbol["LOWIT"].resilience_score == 7
    assert by_symbol["HIGHIT"].resilience_score == 4
    assert by_symbol["HIGHIT"].resilience_score < by_symbol["LOWIT"].resilience_score


def test_etf_without_holdings_keeps_role_based_diversification(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_etf(conn, "BND", "Treasury bond fund", [])

    score = next(s for s in score_all(conn) if s.symbol == "BND")

    # No parsed holdings -> measured diversification is undefined, role default kept.
    assert score.role == "Defensive"
    assert score.diversification_score == 7
