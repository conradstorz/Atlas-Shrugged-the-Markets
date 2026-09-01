"""Tests for repairing an `etf_score` table created before nullable scores.

`connect()` applies the schema with `CREATE TABLE IF NOT EXISTS`, so relaxing
the `NOT NULL` on `etf_score.diversification_score` does nothing to a database
that already exists — the investor's own `.atlas/atlas.db` would keep the old
constraint and reject every unmeasured score. `etf_score` is a pure cache of
values `score_all` recomputes, so it can be rebuilt.

The tables that hold what the investor typed in by hand — `portfolio`,
`portfolio_position`, `decision_journal_entry` — must survive the repair
untouched. That is the assertion this module exists for.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas.db.database import connect

# The `etf_score` table exactly as it was created before this change.
LEGACY_ETF_SCORE_DDL = """
CREATE TABLE etf_score (
    symbol TEXT PRIMARY KEY REFERENCES etf(symbol),
    role TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    ai_score INTEGER NOT NULL,
    resilience_score INTEGER NOT NULL,
    cost_score INTEGER NOT NULL,
    diversification_score INTEGER NOT NULL,
    explanation TEXT NOT NULL
);
"""


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    """Fetch rows as plain tuples; `sqlite3.Row` does not compare equal to one."""
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def _diversification_is_nullable(conn: sqlite3.Connection) -> bool:
    columns = conn.execute("PRAGMA table_info(etf_score)").fetchall()
    return not any(
        column["name"] == "diversification_score" and column["notnull"] for column in columns
    )


def _insert_unmeasured_score(conn: sqlite3.Connection, symbol: str = "AAA") -> None:
    conn.execute("INSERT INTO etf (symbol, description) VALUES (?, ?)", (symbol, "A fund"))
    conn.execute(
        "INSERT INTO etf_score (symbol, role, overall_score, ai_score, resilience_score, "
        "cost_score, diversification_score, explanation) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
        (symbol, "Foundation", 84, 8, 7, 9, "diversification not scored"),
    )
    conn.commit()


def _make_legacy_database(db_path: Path) -> None:
    """Create a database with the old NOT NULL column and investor-entered data."""
    raw = sqlite3.connect(db_path)
    raw.executescript(LEGACY_ETF_SCORE_DDL)
    raw.executescript(
        """
        CREATE TABLE portfolio (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
            notes TEXT
        );
        CREATE TABLE portfolio_position (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            portfolio_id INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
            symbol TEXT NOT NULL,
            description TEXT,
            asset_type TEXT NOT NULL DEFAULT 'ETF',
            market_value REAL NOT NULL,
            notes TEXT,
            UNIQUE (portfolio_id, symbol)
        );
        CREATE TABLE decision_journal_entry (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            entry_date TEXT NOT NULL DEFAULT CURRENT_DATE,
            decision TEXT NOT NULL,
            thesis TEXT NOT NULL,
            confidence INTEGER CHECK (confidence BETWEEN 0 AND 100),
            max_allocation_percent REAL,
            change_mind_conditions TEXT,
            notes TEXT
        );
        INSERT INTO portfolio (id, name, notes) VALUES (1, 'Primary', 'hand-entered');
        INSERT INTO portfolio_position (portfolio_id, symbol, market_value)
            VALUES (1, 'SCHB', 50000);
        INSERT INTO decision_journal_entry (symbol, decision, thesis)
            VALUES ('SCHB', 'buy', 'Own the whole market.');
        """
    )
    raw.commit()
    raw.close()


def test_legacy_database_is_repaired_and_accepts_an_unmeasured_score(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)

    conn = connect(db_path)

    assert _diversification_is_nullable(conn)
    _insert_unmeasured_score(conn)  # would raise IntegrityError against the old column
    stored = conn.execute("SELECT diversification_score FROM etf_score WHERE symbol = 'AAA'").fetchone()
    assert stored["diversification_score"] is None


def test_repair_leaves_investor_entered_tables_alone(tmp_path: Path) -> None:
    """The repair may rebuild the derived cache and nothing else."""
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)

    conn = connect(db_path)

    assert _rows(conn, "SELECT name, notes FROM portfolio") == [("Primary", "hand-entered")]
    assert _rows(conn, "SELECT symbol, market_value FROM portfolio_position") == [("SCHB", 50000.0)]
    assert _rows(conn, "SELECT symbol, decision, thesis FROM decision_journal_entry") == [
        ("SCHB", "buy", "Own the whole market.")
    ]


def test_current_database_is_left_alone(tmp_path: Path) -> None:
    """A database already on the current schema keeps its cached scores."""
    db_path = tmp_path / "atlas.db"
    conn = connect(db_path)
    _insert_unmeasured_score(conn, "BBB")
    conn.close()

    reopened = connect(db_path)

    assert _diversification_is_nullable(reopened)
    assert _rows(reopened, "SELECT symbol FROM etf_score") == [("BBB",)]


def test_repair_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)
    connect(db_path).close()

    conn = connect(db_path)
    _insert_unmeasured_score(conn)
    conn.close()

    # A third open must not drop the rows the second one wrote.
    reopened = connect(db_path)
    assert _rows(reopened, "SELECT symbol FROM etf_score") == [("AAA",)]
