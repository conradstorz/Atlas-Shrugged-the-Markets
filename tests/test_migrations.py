from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas.db.database import connect
from atlas.db.migrations import LATEST_VERSION

# Pre-v0.8 schema, verbatim from git history. Frozen here: migration tests
# must build the exact shape old binaries wrote, not whatever schema.sql
# currently says.
LEGACY_SCHEMA = """
CREATE TABLE IF NOT EXISTS etf (
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

CREATE TABLE IF NOT EXISTS etf_holding (
    etf_symbol TEXT NOT NULL REFERENCES etf(symbol),
    holding_symbol TEXT NOT NULL,
    holding_name TEXT,
    rank INTEGER NOT NULL,
    weight REAL, -- percent of fund, e.g. 6.83 means 6.83%; NULL for seed select-list rows (symbols only)
    source TEXT NOT NULL DEFAULT 'seed_top_ten',
    -- `source` is part of the key so a fund's seed select-list membership row
    -- and its imported holdings-file row for the SAME company can coexist.
    -- With the narrower (etf_symbol, holding_symbol) key, importing a partial
    -- issuer export of a fund's largest names overwrote exactly the seed rows
    -- that mattered and shrank the fund's top ten. Which of the two sources a
    -- fund's top ten is read from is decided by
    -- `atlas.analytics.overlap.TOP_TEN_CTE`, not by the storage key.
    PRIMARY KEY (etf_symbol, holding_symbol, source)
);

CREATE TABLE IF NOT EXISTS etf_score (
    symbol TEXT PRIMARY KEY REFERENCES etf(symbol),
    -- `role` and `ai_score` are keyword heuristics over the fund's description,
    -- so they are always available and stay NOT NULL. Every other score is
    -- nullable, and NULL always means the same thing: not measured, therefore
    -- excluded from overall_score rather than substituted with a stand-in.
    -- 0 is a real score meaning "as bad as this component gets", never a
    -- sentinel for missing data.
    role TEXT NOT NULL,
    -- NULL means no data-grounded component could be measured for this fund
    -- at all, leaving only the AI keyword heuristic, so no overall score was
    -- produced. A number built from a base of 20 plus one keyword heuristic
    -- would look like a measurement and be a guess.
    overall_score INTEGER,
    ai_score INTEGER NOT NULL,
    -- NULL: no information-technology exposure on file, so the role-based
    -- resilience baseline could not be eroded by real data.
    resilience_score INTEGER,
    -- NULL: no gross expense ratio on file.
    cost_score INTEGER,
    -- NULL: no imported holdings file covering essentially the whole fund, so
    -- the fund's breadth is unknown.
    diversification_score INTEGER,
    explanation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_position (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    description TEXT,
    asset_type TEXT NOT NULL DEFAULT 'ETF',
    market_value REAL NOT NULL,
    notes TEXT,
    UNIQUE (portfolio_id, symbol)
);

CREATE TABLE IF NOT EXISTS decision_journal_entry (
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


def make_legacy_db(tmp_path: Path) -> Path:
    db = tmp_path / "atlas.db"
    raw = sqlite3.connect(db)
    raw.executescript(LEGACY_SCHEMA)
    raw.execute(
        "INSERT INTO etf (symbol, description, fund_type, category, select_list,"
        " top_ten_holdings, gross_expense_ratio, information_technology_exposure, source)"
        " VALUES ('SPY', 'S&P 500 broad market', 'ETF', 'Large Blend', 'Y',"
        " '|NVDA||AAPL|', '0.09%', '31%', 'seed')"
    )
    raw.execute(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source)"
        " VALUES ('SPY', 'NVDA', 1, 'seed_top_ten')"
    )
    raw.execute(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, holding_name, rank, weight, source)"
        " VALUES ('SPY', 'NVDA', 'NVIDIA Corp', 1, 7.5, 'holdings_file')"
    )
    raw.execute(
        "INSERT INTO etf_score (symbol, role, overall_score, ai_score, resilience_score,"
        " cost_score, diversification_score, explanation)"
        " VALUES ('SPY', 'Foundation', 77, 8, 6, 10, NULL, 'legacy explanation')"
    )
    raw.commit()
    raw.close()
    return db


def table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
    return {row["name"] for row in rows}


def test_legacy_database_is_normalized_on_connect(tmp_path):
    conn = connect(make_legacy_db(tmp_path))

    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
    names = table_names(conn)
    assert {"asset", "fund", "company", "theme", "fund_holding", "fund_score"} <= names
    assert not {"etf", "etf_holding", "etf_score"} & names

    fund = conn.execute("SELECT * FROM fund WHERE symbol='SPY'").fetchone()
    assert fund["description"] == "S&P 500 broad market"
    assert fund["gross_expense_ratio"] == "0.09%"
    assert fund["information_technology_exposure"] == "31%"
    assert fund["source"] == "seed"
    assert "top_ten_holdings" not in fund.keys()

    spy_asset = conn.execute("SELECT * FROM asset WHERE symbol='SPY'").fetchone()
    assert spy_asset["asset_type"] == "fund"
    assert spy_asset["name"] == "S&P 500 broad market"

    nvda = conn.execute("SELECT * FROM asset WHERE symbol='NVDA'").fetchone()
    assert nvda["asset_type"] == "company"
    assert conn.execute("SELECT 1 FROM company WHERE symbol='NVDA'").fetchone()

    holdings = conn.execute(
        "SELECT * FROM fund_holding WHERE fund_symbol='SPY' ORDER BY source"
    ).fetchall()
    assert len(holdings) == 2
    file_row = [h for h in holdings if h["source"] == "holdings_file"][0]
    assert file_row["weight"] == 7.5
    assert file_row["holding_name"] == "NVIDIA Corp"

    score = conn.execute("SELECT * FROM fund_score WHERE symbol='SPY'").fetchone()
    assert score["overall_score"] == 77
    assert score["diversification_score"] is None
    assert score["explanation"] == "legacy explanation"


def test_fresh_database_is_stamped_without_migrating(tmp_path):
    conn = connect(tmp_path / "fresh.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
    assert "etf" not in table_names(conn)
    # Reopening does not re-run anything and keeps the stamp.
    conn.close()
    conn = connect(tmp_path / "fresh.db")
    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION


# --- edge cases restored from the deleted test_holding_key_migration.py and
# test_schema_repair.py, retargeted at the v0.8 normalization runner ---------

# Pre-widening etf_holding: PK (etf_symbol, holding_symbol), no room for a
# fund's seed select-list row and its imported holdings-file row for the same
# company to coexist. Verbatim from the deleted test_holding_key_migration.py
# (git show 6b735a5:tests/test_holding_key_migration.py), except for the name.
LEGACY_NARROW_KEY_SCHEMA = """
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

# Pre-nullability etf_score: every score column NOT NULL. Verbatim
# (LEGACY_ETF_SCORE_DDL) from the deleted test_schema_repair.py (git show
# 6b735a5:tests/test_schema_repair.py), plus the `etf` table the normalization
# step reads from — test_schema_repair.py never created one because its
# _repair_etf_score_schema didn't need it; the v0.8 runner does.
LEGACY_NOT_NULL_SCORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS etf (
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


def test_narrow_key_legacy_database_migrates(tmp_path):
    """A pre-widening database (PK etf_symbol,holding_symbol) normalizes cleanly."""
    db = tmp_path / "narrow.db"
    raw = sqlite3.connect(db)
    raw.executescript(LEGACY_NARROW_KEY_SCHEMA)  # from deleted test_holding_key_migration.py
    raw.execute(
        "INSERT INTO etf (symbol, description) VALUES ('QQQ', 'Nasdaq 100')"
    )
    raw.execute(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source)"
        " VALUES ('QQQ', 'MSFT', 1, 'seed_top_ten')"
    )
    raw.commit()
    raw.close()
    conn = connect(db)
    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
    row = conn.execute(
        "SELECT * FROM fund_holding WHERE fund_symbol='QQQ' AND holding_symbol='MSFT'"
    ).fetchone()
    assert row["source"] == "seed_top_ten"


def test_not_null_score_legacy_database_migrates(tmp_path):
    """A pre-nullability etf_score (all columns NOT NULL) copies into nullable fund_score."""
    db = tmp_path / "not_null_score.db"
    raw = sqlite3.connect(db)
    raw.executescript(LEGACY_NOT_NULL_SCORE_SCHEMA)
    raw.execute(
        "INSERT INTO etf (symbol, description) VALUES ('SCHB', 'Schwab US Broad Market ETF')"
    )
    raw.execute(
        "INSERT INTO etf_score (symbol, role, overall_score, ai_score, resilience_score,"
        " cost_score, diversification_score, explanation)"
        " VALUES ('SCHB', 'Foundation', 84, 8, 7, 9, 6, 'fully measured')"
    )
    raw.commit()
    raw.close()

    conn = connect(db)

    assert conn.execute("PRAGMA user_version").fetchone()[0] == LATEST_VERSION
    row = conn.execute("SELECT * FROM fund_score WHERE symbol='SCHB'").fetchone()
    assert row["role"] == "Foundation"
    assert row["overall_score"] == 84
    assert row["ai_score"] == 8
    assert row["resilience_score"] == 7
    assert row["cost_score"] == 9
    assert row["diversification_score"] == 6
    assert row["explanation"] == "fully measured"

    nullable = {
        column["name"]
        for column in conn.execute("PRAGMA table_info(fund_score)")
        if not column["notnull"]
    }
    assert {
        "overall_score",
        "resilience_score",
        "cost_score",
        "diversification_score",
    } <= nullable


def test_fund_held_by_fund_gets_no_company_row(tmp_path):
    """A holding symbol that is itself a fund stays fund-typed, no company row."""
    db = make_legacy_db(tmp_path)
    raw = sqlite3.connect(db)
    raw.execute("INSERT INTO etf (symbol, description) VALUES ('VTI', 'Total market')")
    raw.execute(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source)"
        " VALUES ('SPY', 'VTI', 2, 'seed_top_ten')"
    )
    raw.commit()
    raw.close()
    conn = connect(db)
    assert conn.execute("SELECT asset_type FROM asset WHERE symbol='VTI'").fetchone()[0] == "fund"
    assert conn.execute("SELECT 1 FROM company WHERE symbol='VTI'").fetchone() is None


def test_orphan_holding_becomes_stub_fund(tmp_path):
    """A holding row whose fund has no etf row survives as a stub fund's holding."""
    db = tmp_path / "orphan.db"
    raw = sqlite3.connect(db)
    raw.executescript(LEGACY_SCHEMA)
    raw.execute("PRAGMA foreign_keys = OFF")
    raw.execute(
        "INSERT INTO etf_holding (etf_symbol, holding_symbol, holding_name, rank, weight, source)"
        " VALUES ('GHOST', 'AAPL', 'Apple', 1, 5.0, 'holdings_file')"
    )
    raw.commit()
    raw.close()
    conn = connect(db)
    assert conn.execute("SELECT 1 FROM fund WHERE symbol='GHOST'").fetchone()
    assert conn.execute(
        "SELECT weight FROM fund_holding WHERE fund_symbol='GHOST'"
    ).fetchone()[0] == 5.0


def test_investor_tables_survive_migration_untouched(tmp_path):
    """portfolio, portfolio_position, decision_journal_entry rows are byte-identical."""
    db = make_legacy_db(tmp_path)
    raw = sqlite3.connect(db)
    raw.row_factory = sqlite3.Row
    raw.execute("INSERT INTO portfolio (id, name, notes) VALUES (1, 'Primary', 'hand-entered')")
    raw.execute(
        "INSERT INTO portfolio_position (portfolio_id, symbol, market_value) VALUES (1, 'SCHB', 50000)"
    )
    raw.execute(
        "INSERT INTO decision_journal_entry (symbol, decision, thesis) "
        "VALUES ('SCHB', 'buy', 'Own the whole market.')"
    )
    raw.commit()

    # Capture every column of each investor-entered row exactly as inserted
    # (including database-assigned defaults like created_at/entry_date),
    # before the migration runs.
    before_portfolio = dict(raw.execute("SELECT * FROM portfolio WHERE id = 1").fetchone())
    before_position = dict(
        raw.execute("SELECT * FROM portfolio_position WHERE portfolio_id = 1").fetchone()
    )
    before_journal = dict(
        raw.execute("SELECT * FROM decision_journal_entry WHERE symbol = 'SCHB'").fetchone()
    )
    raw.close()

    conn = connect(db)

    after_portfolio = dict(conn.execute("SELECT * FROM portfolio WHERE id = 1").fetchone())
    after_position = dict(
        conn.execute("SELECT * FROM portfolio_position WHERE portfolio_id = 1").fetchone()
    )
    after_journal = dict(
        conn.execute("SELECT * FROM decision_journal_entry WHERE symbol = 'SCHB'").fetchone()
    )

    assert after_portfolio == before_portfolio
    assert after_position == before_position
    assert after_journal == before_journal


def test_migrated_tables_match_fresh_shapes(tmp_path):
    """Drift guard: a migrated DB's new tables have identical shape to a fresh DB's."""
    migrated = connect(make_legacy_db(tmp_path))
    fresh = connect(tmp_path / "fresh.db")
    for table in ("asset", "fund", "company", "theme", "fund_holding", "fund_score"):
        shape = lambda c: [tuple(r) for r in c.execute(f"PRAGMA table_info({table})")]
        assert shape(migrated) == shape(fresh), table


def test_failed_step_rolls_back_and_keeps_version(tmp_path, monkeypatch):
    """A step that raises mid-way leaves user_version and old tables untouched."""
    from atlas.db import migrations
    from atlas.exceptions import AtlasError
    import pytest

    def exploding_step(conn):
        conn.execute("DROP TABLE etf")  # some damage inside the transaction
        raise RuntimeError("boom")

    monkeypatch.setattr(migrations, "STEPS", ((1, exploding_step),))
    db = make_legacy_db(tmp_path)
    with pytest.raises(AtlasError):
        connect(db)
    raw = sqlite3.connect(db)
    assert raw.execute("PRAGMA user_version").fetchone()[0] == 0
    assert raw.execute("SELECT COUNT(*) FROM etf").fetchone()[0] == 1  # rollback restored it
