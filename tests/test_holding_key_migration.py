"""Tests for widening the `etf_holding` primary key to include `source`.

`etf_holding` originally allowed one row per ``(etf_symbol, holding_symbol)``,
so a fund's seed select-list row and its imported holdings-file row for the
same company could not both exist. A partial issuer export of a fund's largest
names therefore consumed exactly the seed rows that mattered, shrinking the
fund's top ten. Widening the key to ``(etf_symbol, holding_symbol, source)``
lets the two kinds of evidence coexist.

SQLite cannot `ALTER` a primary key, so `connect()` rebuilds the table. Unlike
the `etf_score` repair next door, `etf_holding` is NOT derived: it holds issuer
holdings files the investor downloaded by hand and Atlas cannot recreate. The
assertions this module exists for are that **every row survives** the rebuild
and that `portfolio`, `portfolio_position` and `decision_journal_entry` are
never touched.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from atlas.db.database import connect

# The whole schema exactly as it was before this change. Only `etf_holding`'s
# PRIMARY KEY differs from the current `schema.sql`; everything else is
# identical, so a failure here is about the key and nothing else.
LEGACY_SCHEMA = """
CREATE TABLE etf (
    symbol TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    fund_type TEXT,
    category TEXT,
    select_list TEXT,
    top_ten_holdings TEXT,
    gross_expense_ratio TEXT,
    information_technology_exposure TEXT,
    source TEXT
);

CREATE TABLE etf_holding (
    etf_symbol TEXT NOT NULL REFERENCES etf(symbol),
    holding_symbol TEXT NOT NULL,
    holding_name TEXT,
    rank INTEGER NOT NULL,
    weight REAL,
    source TEXT NOT NULL DEFAULT 'seed_top_ten',
    PRIMARY KEY (etf_symbol, holding_symbol)
);

-- `etf_score` on the CURRENT shape, so `_repair_etf_score_schema` has no
-- reason to fire. This fixture exists to test the `etf_holding` rebuild; the
-- point of the assertion below is that the rebuild leaves `etf_score` alone,
-- which only means something if nothing else is rebuilding it either.
CREATE TABLE etf_score (
    symbol TEXT PRIMARY KEY REFERENCES etf(symbol),
    role TEXT NOT NULL,
    overall_score INTEGER,
    ai_score INTEGER NOT NULL,
    resilience_score INTEGER,
    cost_score INTEGER,
    diversification_score INTEGER,
    explanation TEXT NOT NULL
);

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
"""

# Seed select-list membership rows: no weight, no holding name.
LEGACY_SEED_ROWS = [
    ("SCHB", symbol, None, rank, None, "seed_top_ten")
    for rank, symbol in enumerate(
        ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "GOOG", "META", "TSLA", "MU"],
        start=1,
    )
]
# Imported issuer rows for a different fund, so the legacy narrow key does not
# force the fixture itself to choose between the two sources.
LEGACY_IMPORTED_ROWS = [
    ("DIVB", "ADP", "Automatic Data Processing", 1, 8.25, "holdings_file"),
    ("DIVB", "IBM", "International Business Machines", 2, 6.10, "holdings_file"),
    ("DIVB", "XOM", "Exxon Mobil Corp", 3, -1.20, "holdings_file"),
]
# A hand-written row with an unrecognized source. `source` carries no CHECK
# constraint, and a migration that silently dropped such a row would be
# destroying data just the same.
LEGACY_ODD_ROWS = [("DIVB", "HANDX", "Hand entered", 4, None, "hand_edited")]

ALL_LEGACY_HOLDINGS = LEGACY_SEED_ROWS + LEGACY_IMPORTED_ROWS + LEGACY_ODD_ROWS


def _make_legacy_database(db_path: Path) -> None:
    """Build a database on the OLD schema with data in every table."""
    raw = sqlite3.connect(db_path)
    raw.executescript(LEGACY_SCHEMA)
    raw.executemany(
        "INSERT INTO etf (symbol, description) VALUES (?, ?)",
        [("SCHB", "Schwab US Broad Market ETF"), ("DIVB", "iShares Core Dividend ETF")],
    )
    raw.executemany(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, holding_name, rank, weight, source) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        ALL_LEGACY_HOLDINGS,
    )
    raw.execute(
        "INSERT INTO etf_score (symbol, role, overall_score, ai_score, resilience_score, "
        "cost_score, diversification_score, explanation) "
        "VALUES ('SCHB', 'Foundation', 84, 8, 7, 9, NULL, 'why')"
    )
    raw.execute("INSERT INTO portfolio (id, name, notes) VALUES (1, 'Primary', 'hand-entered')")
    raw.execute(
        "INSERT INTO portfolio_position (portfolio_id, symbol, market_value) VALUES (1, 'SCHB', 50000)"
    )
    raw.execute(
        "INSERT INTO decision_journal_entry (symbol, decision, thesis) "
        "VALUES ('SCHB', 'buy', 'Own the whole market.')"
    )
    raw.commit()
    raw.close()


def _holding_rows(conn: sqlite3.Connection) -> list[tuple]:
    """Every holding row as plain tuples; `sqlite3.Row` does not compare equal to one."""
    return [
        tuple(row)
        for row in conn.execute(
            "SELECT etf_symbol, holding_symbol, holding_name, rank, weight, source "
            "FROM etf_holding ORDER BY etf_symbol, source, holding_symbol"
        )
    ]


def _primary_key_columns(conn: sqlite3.Connection, table: str) -> list[str]:
    """Return a table's primary-key column names, in key order.

    ``PRAGMA table_info``'s ``pk`` is the 1-based position of the column within
    the primary key, and 0 for a column outside it.
    """
    columns = [dict(row) for row in conn.execute(f"PRAGMA table_info({table})")]
    keyed = [column for column in columns if column["pk"]]
    return [column["name"] for column in sorted(keyed, key=lambda column: column["pk"])]


def test_migration_preserves_every_holding_row(tmp_path: Path) -> None:
    """No row may be lost: count and contents, across all three sources."""
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)

    conn = connect(db_path)

    count = conn.execute("SELECT COUNT(*) AS c FROM etf_holding").fetchone()["c"]
    assert count == len(ALL_LEGACY_HOLDINGS)
    assert _holding_rows(conn) == sorted(ALL_LEGACY_HOLDINGS, key=lambda row: (row[0], row[5], row[1]))


def test_migration_widens_the_primary_key(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)

    conn = connect(db_path)

    assert _primary_key_columns(conn, "etf_holding") == [
        "etf_symbol",
        "holding_symbol",
        "source",
    ]


def test_the_two_sources_can_now_hold_the_same_symbol(tmp_path: Path) -> None:
    """The point of the widening: seed membership and a real weight coexist."""
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)
    conn = connect(db_path)

    conn.execute(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, weight, source) "
        "VALUES ('SCHB', 'NVDA', 1, 7.03, 'holdings_file')"
    )
    conn.commit()

    rows = conn.execute(
        "SELECT source, weight FROM etf_holding "
        "WHERE etf_symbol = 'SCHB' AND holding_symbol = 'NVDA' ORDER BY source"
    ).fetchall()
    assert [(row["source"], row["weight"]) for row in rows] == [
        ("holdings_file", 7.03),
        ("seed_top_ten", None),
    ]


def test_the_widened_key_still_rejects_a_duplicate_within_one_source(tmp_path: Path) -> None:
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)
    conn = connect(db_path)

    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source) "
            "VALUES ('SCHB', 'NVDA', 99, 'seed_top_ten')"
        )


def test_migration_leaves_investor_entered_tables_untouched(tmp_path: Path) -> None:
    """`portfolio`, `portfolio_position` and `decision_journal_entry` are hand-typed."""
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)

    conn = connect(db_path)

    assert [tuple(row) for row in conn.execute("SELECT id, name, notes FROM portfolio")] == [
        (1, "Primary", "hand-entered")
    ]
    assert [
        tuple(row)
        for row in conn.execute("SELECT portfolio_id, symbol, market_value FROM portfolio_position")
    ] == [(1, "SCHB", 50000.0)]
    assert [
        tuple(row)
        for row in conn.execute("SELECT symbol, decision, thesis FROM decision_journal_entry")
    ] == [("SCHB", "buy", "Own the whole market.")]


def test_migration_preserves_the_other_derived_tables(tmp_path: Path) -> None:
    """`etf` and `etf_score` are not the migration's target and keep their rows."""
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)

    conn = connect(db_path)

    assert [tuple(row) for row in conn.execute("SELECT symbol FROM etf ORDER BY symbol")] == [
        ("DIVB",),
        ("SCHB",),
    ]
    assert [tuple(row) for row in conn.execute("SELECT symbol, role FROM etf_score")] == [
        ("SCHB", "Foundation")
    ]


def test_foreign_key_to_etf_still_enforces_after_migration(tmp_path: Path) -> None:
    """The rebuild must not quietly drop `REFERENCES etf(symbol)`, nor leave FKs off."""
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)
    conn = connect(db_path)

    assert conn.execute("PRAGMA foreign_keys").fetchone()[0] == 1
    with pytest.raises(sqlite3.IntegrityError):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source) "
            "VALUES ('NOSUCHFUND', 'AAPL', 1, 'seed_top_ten')"
        )
    assert conn.execute("PRAGMA foreign_key_check(etf_holding)").fetchall() == []


def test_migration_is_a_no_op_on_an_already_migrated_database(tmp_path: Path) -> None:
    """Re-opening must not rebuild again, and must not lose rows written since."""
    db_path = tmp_path / "legacy.db"
    _make_legacy_database(db_path)
    connect(db_path).close()

    second = connect(db_path)
    second.execute(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, weight, source) "
        "VALUES ('SCHB', 'NVDA', 1, 7.03, 'holdings_file')"
    )
    second.commit()
    second.close()

    third = connect(db_path)
    assert third.execute("SELECT COUNT(*) AS c FROM etf_holding").fetchone()["c"] == (
        len(ALL_LEGACY_HOLDINGS) + 1
    )
    assert _primary_key_columns(third, "etf_holding") == [
        "etf_symbol",
        "holding_symbol",
        "source",
    ]


def test_migrated_table_matches_a_freshly_created_one(tmp_path: Path) -> None:
    """The rebuild's DDL must not drift from `schema.sql`."""
    legacy_path = tmp_path / "legacy.db"
    _make_legacy_database(legacy_path)
    migrated = connect(legacy_path)
    fresh = connect(tmp_path / "fresh.db")

    def shape(conn: sqlite3.Connection) -> list[tuple]:
        return [
            (row["name"], row["type"], row["notnull"], row["dflt_value"], row["pk"])
            for row in conn.execute("PRAGMA table_info(etf_holding)")
        ]

    assert shape(migrated) == shape(fresh)
    assert [tuple(row) for row in migrated.execute("PRAGMA foreign_key_list(etf_holding)")] == [
        tuple(row) for row in fresh.execute("PRAGMA foreign_key_list(etf_holding)")
    ]


def test_a_fresh_database_is_created_on_the_widened_key(tmp_path: Path) -> None:
    """A brand-new database needs no migration at all."""
    conn = connect(tmp_path / "atlas.db")

    assert _primary_key_columns(conn, "etf_holding") == [
        "etf_symbol",
        "holding_symbol",
        "source",
    ]



def test_an_unfamiliar_primary_key_is_left_untouched(tmp_path: Path) -> None:
    """The widening migration must fire only on the exact legacy key.

    It rewrites a table holding issuer files the investor downloaded by hand.
    A key this migration does not recognize may encode a property that
    rebuilding to the assumed shape would silently discard, so an unfamiliar
    shape is left alone rather than migrated on a guess.
    """
    db = tmp_path / "custom.db"
    raw = sqlite3.connect(db)
    raw.executescript(
        """
        CREATE TABLE etf (symbol TEXT PRIMARY KEY, description TEXT NOT NULL);
        CREATE TABLE etf_holding (
            etf_symbol TEXT NOT NULL REFERENCES etf(symbol),
            holding_symbol TEXT NOT NULL,
            holding_name TEXT,
            rank INTEGER NOT NULL,
            weight REAL,
            source TEXT NOT NULL DEFAULT 'seed_top_ten',
            PRIMARY KEY (etf_symbol, holding_symbol, rank)
        );
        INSERT INTO etf VALUES ('AAA', 'A fund');
        INSERT INTO etf_holding VALUES ('AAA', 'NVDA', 'NVIDIA', 1, 7.0, 'holdings_file');
        """
    )
    raw.commit()
    raw.close()

    conn = connect(db)

    key = [c["name"] for c in sorted(conn.execute("PRAGMA table_info(etf_holding)"), key=lambda c: c["pk"]) if c["pk"]]
    assert key == ["etf_symbol", "holding_symbol", "rank"], "unfamiliar key must survive untouched"
    assert conn.execute("SELECT COUNT(*) AS c FROM etf_holding").fetchone()["c"] == 1
    conn.close()
