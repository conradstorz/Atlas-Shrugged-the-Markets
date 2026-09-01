"""Tests for repairing an `etf_score` table created before nullable scores.

`connect()` applies the schema with `CREATE TABLE IF NOT EXISTS`, so relaxing
a `NOT NULL` on one of `etf_score`'s score columns does nothing to a database
that already exists — the investor's own `.atlas/atlas.db` would keep the old
constraint and reject every unmeasured score. `etf_score` is a pure cache of
values `score_all` recomputes, so it can be rebuilt.

The columns were relaxed in two rounds: `diversification_score` first (issue
#6), then `overall_score`, `resilience_score` and `cost_score` (issue #10). So
there are two legacy shapes in the wild and both are covered here, including
the intermediate one a database created between the changes would carry.

The tables that hold what the investor typed in by hand — `portfolio`,
`portfolio_position`, `decision_journal_entry` — must survive the repair
untouched. That is the assertion this module exists for.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas.db.database import connect

# The `etf_score` table as it was before any score column became nullable.
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

# The intermediate shape: `diversification_score` relaxed by issue #6, the
# other three still NOT NULL. A database created between the two changes has
# this, and it is the shape that would go on rejecting every unscored fund if
# the repair only ever looked at `diversification_score`.
POST_ISSUE_6_ETF_SCORE_DDL = """
CREATE TABLE etf_score (
    symbol TEXT PRIMARY KEY REFERENCES etf(symbol),
    role TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    ai_score INTEGER NOT NULL,
    resilience_score INTEGER NOT NULL,
    cost_score INTEGER NOT NULL,
    diversification_score INTEGER,
    explanation TEXT NOT NULL
);
"""


def _rows(conn: sqlite3.Connection, sql: str) -> list[tuple]:
    """Fetch rows as plain tuples; `sqlite3.Row` does not compare equal to one."""
    return [tuple(row) for row in conn.execute(sql).fetchall()]


def _nullable_columns(conn: sqlite3.Connection) -> set[str]:
    """The `etf_score` columns that currently accept NULL."""
    return {
        column["name"]
        for column in conn.execute("PRAGMA table_info(etf_score)").fetchall()
        if not column["notnull"]
    }


def _diversification_is_nullable(conn: sqlite3.Connection) -> bool:
    return "diversification_score" in _nullable_columns(conn)


def _insert_unmeasured_score(conn: sqlite3.Connection, symbol: str = "AAA") -> None:
    conn.execute("INSERT INTO etf (symbol, description) VALUES (?, ?)", (symbol, "A fund"))
    conn.execute(
        "INSERT INTO etf_score (symbol, role, overall_score, ai_score, resilience_score, "
        "cost_score, diversification_score, explanation) VALUES (?, ?, ?, ?, ?, ?, NULL, ?)",
        (symbol, "Foundation", 84, 8, 7, 9, "diversification not scored"),
    )
    conn.commit()


def _insert_unscored_fund(conn: sqlite3.Connection, symbol: str = "CCC") -> None:
    """Store a fund with no measurable component at all: every score column NULL."""
    conn.execute("INSERT INTO etf (symbol, description) VALUES (?, ?)", (symbol, "A fund"))
    conn.execute(
        "INSERT INTO etf_score (symbol, role, overall_score, ai_score, resilience_score, "
        "cost_score, diversification_score, explanation) "
        "VALUES (?, ?, NULL, ?, NULL, NULL, NULL, ?)",
        (symbol, "Foundation", 8, "Not scored: no expense ratio, ..."),
    )
    conn.commit()


def _make_legacy_database(db_path: Path, etf_score_ddl: str = LEGACY_ETF_SCORE_DDL) -> None:
    """Create a database on an old `etf_score` shape, with investor-entered data."""
    raw = sqlite3.connect(db_path)
    raw.executescript(etf_score_ddl)
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


# --- issue #10: the other three score columns become nullable too -------------

EXPECTED_NULLABLE = {
    "overall_score",
    "resilience_score",
    "cost_score",
    "diversification_score",
}


def test_post_issue_6_database_is_repaired_for_the_remaining_columns(tmp_path: Path) -> None:
    """The intermediate shape must be repaired, not mistaken for the current one.

    Its `diversification_score` is already nullable, so a check that looked at
    that column alone would find nothing to do and leave `overall_score`,
    `resilience_score` and `cost_score` rejecting every unscored fund.
    """
    db_path = tmp_path / "post6.db"
    _make_legacy_database(db_path, POST_ISSUE_6_ETF_SCORE_DDL)

    conn = connect(db_path)

    assert EXPECTED_NULLABLE <= _nullable_columns(conn)
    _insert_unscored_fund(conn)  # would raise IntegrityError against the old columns
    stored = conn.execute(
        "SELECT overall_score, resilience_score, cost_score, diversification_score "
        "FROM etf_score WHERE symbol = 'CCC'"
    ).fetchone()
    assert tuple(stored) == (None, None, None, None)


def test_post_issue_6_repair_leaves_investor_entered_tables_alone(tmp_path: Path) -> None:
    db_path = tmp_path / "post6.db"
    _make_legacy_database(db_path, POST_ISSUE_6_ETF_SCORE_DDL)

    conn = connect(db_path)

    assert _rows(conn, "SELECT name, notes FROM portfolio") == [("Primary", "hand-entered")]
    assert _rows(conn, "SELECT symbol, market_value FROM portfolio_position") == [("SCHB", 50000.0)]
    assert _rows(conn, "SELECT symbol, decision, thesis FROM decision_journal_entry") == [
        ("SCHB", "buy", "Own the whole market.")
    ]


def test_fully_legacy_database_is_repaired_for_every_score_column(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)

    conn = connect(db_path)

    assert EXPECTED_NULLABLE <= _nullable_columns(conn)
    _insert_unscored_fund(conn)


def test_repaired_database_still_requires_role_ai_score_and_explanation(tmp_path: Path) -> None:
    """Relaxing the score columns must not relax the ones always known."""
    db_path = tmp_path / "post6.db"
    _make_legacy_database(db_path, POST_ISSUE_6_ETF_SCORE_DDL)

    conn = connect(db_path)

    # `symbol` is a TEXT PRIMARY KEY, which SQLite does not itself mark NOT
    # NULL, so it is expected in this set and is not a score column.
    assert _nullable_columns(conn) == EXPECTED_NULLABLE | {"symbol"}
    assert not {"role", "ai_score", "explanation"} & _nullable_columns(conn)


def test_post_issue_6_repair_is_idempotent(tmp_path: Path) -> None:
    db_path = tmp_path / "post6.db"
    _make_legacy_database(db_path, POST_ISSUE_6_ETF_SCORE_DDL)
    connect(db_path).close()

    conn = connect(db_path)
    _insert_unscored_fund(conn)
    conn.close()

    # A third open must not drop the row the second one wrote.
    reopened = connect(db_path)
    assert _rows(reopened, "SELECT symbol FROM etf_score") == [("CCC",)]
