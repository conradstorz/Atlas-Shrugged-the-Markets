# v0.8 Normalized Schema Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the prototype `etf`/`etf_holding`/`etf_score` tables with normalized `asset`/`fund`/`company`/`theme`/`fund_holding`/`fund_score` tables, migrating existing databases in place via a `PRAGMA user_version` runner, with every CLI command's behavior and output unchanged.

**Architecture:** `asset` is the supertype registry of every symbol; `fund` and `company` are subtype tables keyed by the same symbol. A new `src/atlas/db/migrations.py` owns a versioned migration runner called from `connect()`, replacing the two ad-hoc introspection repairs. All six SQL-touching modules are re-pointed at the new tables in one flag-day task, driven by a failing end-to-end migration test.

**Tech Stack:** Python ≥3.11, sqlite3 stdlib, Typer CLI, FastAPI web, pytest via `uv run pytest`.

**Spec:** `docs/superpowers/specs/2026-09-12-normalized-schema-v0_8-design.md`

**Deviation from spec (approved rationale):** The spec folds the two existing repairs in as migration steps 1–2. That cannot work as written: `_repair_etf_score_schema` re-runs `schema.sql`, which after this change no longer contains `etf_score`. Both repairs are also subsumed by the normalization step, which copies by column name into fresh tables that already have the wide key and nullable score columns. So the runner ships with a single step (`user_version` 0→1). The old repairs' test intent (legacy narrow-key `etf_holding`, legacy NOT-NULL `etf_score`) is preserved as migration-input test cases in Task 3.

## Global Constraints

- No investment concepts in `platform/`, `application/`, `plugins/`, `exceptions.py` (Kernel boundary, ADR-0002). All new code goes under `src/atlas/db/` and the existing domain modules.
- Command names, flags, dataclasses, and printed output stay identical. SQL-only changes in consumers.
- Never lose investor-entered data: `portfolio`, `portfolio_position`, `decision_journal_entry` are untouched by migration; `fund_holding` rows are hand-downloaded issuer files and must survive migration byte-for-byte.
- NULL score semantics unchanged: NULL = "not measured", never a default. 0 is a real score.
- `weight` semantics unchanged: percent of fund (6.83 = 6.83%), NULL for seed rows.
- Migration must be atomic: on any failure, rollback, raise `AtlasError`, leave `user_version` unchanged.
- Use `uv run pytest` for all test runs. No `&&` chaining in commands.
- Do not modify `SCORER_VERSION` (`src/atlas/scoring/model.py`) — scoring logic is untouched.

---

### Task 1: Test fixture helpers

Mechanical refactor so the flag-day in Task 2 touches one helper module instead of 43 insert sites. Helpers write the OLD tables in this task; Task 2 flips their internals.

**Files:**
- Create: `tests/db_fixtures.py`
- Modify: every test file containing `INSERT INTO etf`, `INSERT INTO etf_holding`, or `INSERT INTO etf_score` (11 files, ~43 sites — find them with `grep -rn "INSERT INTO etf" tests/`)
- Do NOT touch: `tests/test_holding_key_migration.py` and `tests/test_schema_repair.py` legacy-DDL fixtures (`LEGACY_SCHEMA`, `_make_legacy_database`) — those deliberately bypass `connect()` and are replaced wholesale in Tasks 2–3.

**Interfaces:**
- Produces (used by every later task's tests):
  - `add_fund(conn, symbol, description="", *, fund_type=None, category=None, select_list=None, gross_expense_ratio=None, information_technology_exposure=None, source=None) -> None`
  - `add_holding(conn, fund_symbol, holding_symbol, *, holding_name=None, rank=1, weight=None, source="seed_top_ten") -> None` — must also satisfy any FK the holding needs (none in the old schema; Task 2 makes it create stub rows)
  - `add_score(conn, symbol, *, role="Satellite", overall_score=None, ai_score=4, resilience_score=None, cost_score=None, diversification_score=None, explanation="test") -> None`
- Consumes: nothing.

- [ ] **Step 1: Write `tests/db_fixtures.py`**

```python
"""Insert universe fixtures through one seam so schema changes touch one file.

These write whatever tables the current schema uses. Tests express *what*
exists (a fund, a holding, a score), not which tables store it.
"""
from __future__ import annotations

import sqlite3


def add_fund(
    conn: sqlite3.Connection,
    symbol: str,
    description: str = "",
    *,
    fund_type: str | None = None,
    category: str | None = None,
    select_list: str | None = None,
    gross_expense_ratio: str | None = None,
    information_technology_exposure: str | None = None,
    source: str | None = None,  # None matches what raw fixture INSERTs left in the column
) -> None:
    conn.execute(
        """
        INSERT INTO etf (
            symbol, description, fund_type, category, select_list,
            gross_expense_ratio, information_technology_exposure, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            description=excluded.description,
            fund_type=excluded.fund_type,
            category=excluded.category,
            select_list=excluded.select_list,
            gross_expense_ratio=excluded.gross_expense_ratio,
            information_technology_exposure=excluded.information_technology_exposure,
            source=excluded.source
        """,
        (symbol, description, fund_type, category, select_list,
         gross_expense_ratio, information_technology_exposure, source),
    )


def add_holding(
    conn: sqlite3.Connection,
    fund_symbol: str,
    holding_symbol: str,
    *,
    holding_name: str | None = None,
    rank: int = 1,
    weight: float | None = None,
    source: str = "seed_top_ten",
) -> None:
    conn.execute(
        """
        INSERT INTO etf_holding (
            etf_symbol, holding_symbol, holding_name, rank, weight, source
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (fund_symbol, holding_symbol, holding_name, rank, weight, source),
    )


def add_score(
    conn: sqlite3.Connection,
    symbol: str,
    *,
    role: str = "Satellite",
    overall_score: int | None = None,
    ai_score: int = 4,
    resilience_score: int | None = None,
    cost_score: int | None = None,
    diversification_score: int | None = None,
    explanation: str = "test",
) -> None:
    conn.execute(
        """
        INSERT INTO etf_score (
            symbol, role, overall_score, ai_score, resilience_score,
            cost_score, diversification_score, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (symbol, role, overall_score, ai_score, resilience_score,
         cost_score, diversification_score, explanation),
    )
```

- [ ] **Step 2: Rewrite the fixture insert sites**

For each `INSERT INTO etf...` site in tests (skip the two legacy-DDL migration test files), replace the raw SQL with the matching helper call. Rules:
- A fixture that sets `top_ten_holdings` (the raw pipe-string): drop that argument — check first that the test does not read the column back (grep the test for `top_ten_holdings`); if one does, it is asserting on the raw string and must instead assert on `add_holding`-created rows. Flag any such test in the commit message.
- A fixture inserting into `etf` only to satisfy the `etf_holding` FK keeps using `add_fund(conn, symbol)` with defaults.
- Preserve each site's exact column values otherwise.

- [ ] **Step 3: Run the full suite**

Run: `uv run pytest`
Expected: all tests pass, identical count to before the refactor.

- [ ] **Step 4: Commit**

```bash
git add tests/
git commit -m "test: route universe fixtures through tests/db_fixtures.py"
```

---

### Task 2: Flag-day cutover — new schema, migration runner, all consumers

One task because the change is atomic: no intermediate state keeps the suite green. TDD driver: the end-to-end migration test is written first and fails until everything lands.

**Files:**
- Create: `src/atlas/db/migrations.py`
- Create: `tests/test_migrations.py`
- Rewrite: `src/atlas/db/schema.sql`
- Modify: `src/atlas/db/database.py` (connect, loaders, forget_fund; delete `_repair_etf_score_schema`, `_widen_etf_holding_key`, `ETF_HOLDING_COLUMNS`, `LEGACY_ETF_HOLDING_KEY`, `NULLABLE_ETF_SCORE_COLUMNS`, `ETF_HOLDING_REBUILD_DDL`)
- Modify: `src/atlas/scoring/engine.py:95-102, 355-362, 385, 391-416`
- Modify: `src/atlas/analytics/overlap.py:52-102` (TOP_TEN_CTE)
- Modify: `src/atlas/portfolio/analysis.py:121-151, 228-232`
- Modify: `src/atlas/cli/main.py:203-205, 223-227`
- Modify: `src/atlas/web/app.py:125, 203`
- Modify: `tests/db_fixtures.py` (flip to new tables)
- Delete: `tests/test_holding_key_migration.py`, `tests/test_schema_repair.py` (intent restored in this task's driver test and Task 3)

**Interfaces:**
- Produces:
  - `atlas.db.migrations.migrate(conn: sqlite3.Connection) -> None` — called only by `connect()`
  - `atlas.db.migrations.LATEST_VERSION: int` (= 1)
  - Tables `asset(symbol, name, asset_type)`, `fund(symbol, description, fund_type, category, select_list, gross_expense_ratio, information_technology_exposure, source)`, `company(symbol)`, `theme(id, name, description)`, `fund_holding(fund_symbol, holding_symbol, holding_name, rank, weight, source)`, `fund_score(symbol, role, overall_score, ai_score, resilience_score, cost_score, diversification_score, explanation)`
- Consumes: Task 1's fixture helpers (flipped here).
- Unchanged public API: `connect`, `load_seed_universe`, `load_portfolio_csv`, `load_fund_holdings`, `forget_fund`, `ForgetFundResult`, `score_all`, `read_scores`, `measured_diversification`, `top_ten_holdings`, `holdings_weight_source`, `compare_etfs`, `top_repeated_holdings`, `universe_coverage`, `combined_concentration` — same signatures, same return shapes.

- [ ] **Step 1: Write the failing end-to-end migration test**

`tests/test_migrations.py`. The legacy DDL is the pre-v0.8 `schema.sql` verbatim (copy it from `git show HEAD:src/atlas/db/schema.sql` while it still exists — that is the current file content before this task edits it).

```python
from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas.db.database import connect
from atlas.db.migrations import LATEST_VERSION

# Pre-v0.8 schema, verbatim from git history. Frozen here: migration tests
# must build the exact shape old binaries wrote, not whatever schema.sql
# currently says.
LEGACY_SCHEMA = """
<paste the full pre-task content of src/atlas/db/schema.sql here>
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
```

- [ ] **Step 2: Run it to verify it fails**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas.db.migrations'`.

- [ ] **Step 3: Rewrite `src/atlas/db/schema.sql`**

Full new content (replaces the file):

```sql
CREATE TABLE IF NOT EXISTS asset (
    symbol      TEXT PRIMARY KEY,
    name        TEXT,                          -- NULL allowed for stub rows created by holdings import
    asset_type  TEXT NOT NULL CHECK (asset_type IN ('fund', 'company'))
);

CREATE TABLE IF NOT EXISTS fund (
    symbol                  TEXT PRIMARY KEY REFERENCES asset(symbol),
    description             TEXT NOT NULL,
    fund_type               TEXT,
    category                TEXT,
    select_list             TEXT,
    gross_expense_ratio     TEXT,
    information_technology_exposure TEXT,
    source                  TEXT               -- NULL = stub created by import-holdings; the CLI phantom-fund warning keys off this
);

CREATE TABLE IF NOT EXISTS company (
    symbol  TEXT PRIMARY KEY REFERENCES asset(symbol)
    -- no attributes yet; exists so v0.9 themes/sector have an anchor
);

CREATE TABLE IF NOT EXISTS theme (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
    -- empty in v0.8; v0.9 fills it and adds theme_link
);

CREATE TABLE IF NOT EXISTS fund_holding (
    fund_symbol     TEXT NOT NULL REFERENCES fund(symbol),
    holding_symbol  TEXT NOT NULL REFERENCES asset(symbol),
    holding_name    TEXT,
    rank            INTEGER NOT NULL,
    weight          REAL, -- percent of fund, e.g. 6.83 means 6.83%; NULL for seed select-list rows (symbols only)
    source          TEXT NOT NULL DEFAULT 'seed_top_ten',
    -- `source` is part of the key so a fund's seed select-list membership row
    -- and its imported holdings-file row for the SAME company can coexist.
    -- Which of the two sources a fund's top ten is read from is decided by
    -- `atlas.analytics.overlap.TOP_TEN_CTE`, not by the storage key.
    PRIMARY KEY (fund_symbol, holding_symbol, source)
);

CREATE TABLE IF NOT EXISTS fund_score (
    symbol TEXT PRIMARY KEY REFERENCES fund(symbol),
    -- `role` and `ai_score` are keyword heuristics over the fund's description,
    -- so they are always available and stay NOT NULL. Every other score is
    -- nullable, and NULL always means the same thing: not measured, therefore
    -- excluded from overall_score rather than substituted with a stand-in.
    role TEXT NOT NULL,
    overall_score INTEGER,
    ai_score INTEGER NOT NULL,
    resilience_score INTEGER,
    cost_score INTEGER,
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
```

(`portfolio`, `portfolio_position`, `decision_journal_entry` are the investor-entered tables: copy their blocks over from the old file **unchanged, verbatim**.)

- [ ] **Step 4: Write `src/atlas/db/migrations.py`**

```python
"""Versioned, in-place schema migrations, run once per database by `connect()`.

`PRAGMA user_version` records which migrations a database has been through.
`connect()` first runs `schema.sql` (all `CREATE TABLE IF NOT EXISTS`, so a
legacy database gains the new empty tables alongside its old ones), then calls
:func:`migrate`, which runs every step above the stored version, in order,
each in its own transaction. A fresh database has nothing to migrate and is
stamped `LATEST_VERSION` immediately.

Steps never lose investor data: `portfolio`, `portfolio_position` and
`decision_journal_entry` are not referenced by any step, holdings rows are
copied with row-count guards, and any failure rolls the step back and leaves
`user_version` untouched, so the database stays usable by the previous binary.
"""
from __future__ import annotations

import sqlite3

from atlas.exceptions import AtlasError

LATEST_VERSION = 1


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= LATEST_VERSION:
        return
    if version == 0 and not _table_exists(conn, "etf"):
        # Fresh database: schema.sql just created the current tables and
        # there is no prototype data to normalize. Stamp and return.
        conn.execute(f"PRAGMA user_version = {LATEST_VERSION}")
        conn.commit()
        return
    for target, step in STEPS:
        if version < target:
            _run_step(conn, target, step)
            version = target


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _run_step(conn: sqlite3.Connection, target: int, step) -> None:
    conn.commit()  # Leave any implicit transaction before touching PRAGMAs.
    foreign_keys_were_on = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    # A PRAGMA is a no-op inside a transaction, so this must precede BEGIN.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        try:
            step(conn)
            # user_version lives in the database header and is transactional:
            # a rollback reverts the stamp along with the step's changes.
            conn.execute(f"PRAGMA user_version = {target}")
            conn.commit()
        except BaseException as exc:
            conn.rollback()
            if isinstance(exc, AtlasError):
                raise
            raise AtlasError(
                f"Migration to schema version {target} failed and was rolled back; "
                f"the database is unchanged: {exc}"
            ) from exc
    finally:
        if foreign_keys_were_on:
            conn.execute("PRAGMA foreign_keys = ON")


def _normalize_universe(conn: sqlite3.Connection) -> None:
    """v0.8: etf/etf_holding/etf_score -> asset/fund/company/fund_holding/fund_score.

    Copies by column name into the new tables, then drops the old ones. Handles
    every legacy shape in one pass: a narrow-key `etf_holding` copies cleanly
    because the wide key is a superset, and a NOT-NULL-era `etf_score` copies
    cleanly because the new columns are nullable. Pre-existing orphan holdings
    (an `etf_holding` row whose fund has no `etf` row) become stub funds rather
    than being dropped — they are the investor's data.
    """
    holding_count = _count(conn, "etf_holding") if _table_exists(conn, "etf_holding") else 0
    score_count = _count(conn, "etf_score") if _table_exists(conn, "etf_score") else 0

    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) "
        "SELECT symbol, description, 'fund' FROM etf"
    )
    conn.execute(
        """
        INSERT INTO fund (
            symbol, description, fund_type, category, select_list,
            gross_expense_ratio, information_technology_exposure, source
        )
        SELECT symbol, description, fund_type, category, select_list,
               gross_expense_ratio, information_technology_exposure, source
        FROM etf
        """
    )
    if _table_exists(conn, "etf_holding"):
        # Orphan fund symbols first (rows referencing a missing etf), so they
        # win the 'fund' type over the company-stub insert below.
        conn.execute(
            "INSERT INTO asset (symbol, name, asset_type) "
            "SELECT DISTINCT etf_symbol, '', 'fund' FROM etf_holding "
            "WHERE etf_symbol NOT IN (SELECT symbol FROM asset)"
        )
        conn.execute(
            "INSERT INTO fund (symbol, description) "
            "SELECT DISTINCT etf_symbol, '' FROM etf_holding "
            "WHERE etf_symbol NOT IN (SELECT symbol FROM fund)"
        )
        conn.execute(
            "INSERT INTO asset (symbol, name, asset_type) "
            "SELECT holding_symbol, MAX(holding_name), 'company' FROM etf_holding "
            "WHERE holding_symbol NOT IN (SELECT symbol FROM asset) "
            "GROUP BY holding_symbol"
        )
        conn.execute(
            "INSERT INTO company (symbol) "
            "SELECT symbol FROM asset WHERE asset_type = 'company'"
        )
        conn.execute(
            """
            INSERT INTO fund_holding (
                fund_symbol, holding_symbol, holding_name, rank, weight, source
            )
            SELECT etf_symbol, holding_symbol, holding_name, rank, weight, source
            FROM etf_holding
            """
        )
    if _table_exists(conn, "etf_score"):
        conn.execute(
            """
            INSERT INTO fund_score (
                symbol, role, overall_score, ai_score, resilience_score,
                cost_score, diversification_score, explanation
            )
            SELECT symbol, role, overall_score, ai_score, resilience_score,
                   cost_score, diversification_score, explanation
            FROM etf_score
            """
        )

    copied_holdings = _count(conn, "fund_holding")
    if copied_holdings != holding_count:
        raise AtlasError(
            "Refusing to normalize: fund_holding holds "
            f"{copied_holdings} rows, not the {holding_count} etf_holding had. "
            "Nothing was changed."
        )
    copied_scores = _count(conn, "fund_score")
    if copied_scores != score_count:
        raise AtlasError(
            "Refusing to normalize: fund_score holds "
            f"{copied_scores} rows, not the {score_count} etf_score had. "
            "Nothing was changed."
        )
    for table in ("asset", "fund", "company", "fund_holding", "fund_score"):
        orphans = conn.execute(f"PRAGMA foreign_key_check({table})").fetchall()
        if orphans:
            raise AtlasError(
                f"Refusing to normalize: {len(orphans)} {table} row(s) would "
                "reference a missing row. Nothing was changed."
            )

    if _table_exists(conn, "etf_holding"):
        conn.execute("DROP TABLE etf_holding")
    if _table_exists(conn, "etf_score"):
        conn.execute("DROP TABLE etf_score")
    conn.execute("DROP TABLE etf")


STEPS: tuple[tuple[int, object], ...] = ((1, _normalize_universe),)
```

Note: `migrate` is called by `connect()` after `row_factory = sqlite3.Row` is set, but every fetch here indexes by position (`[0]`) or name-independent PRAGMA rows, so it also works on a raw connection in tests.

- [ ] **Step 5: Rewrite `src/atlas/db/database.py`**

`connect()` becomes:

```python
def connect(db_path: Path) -> sqlite3.Connection:
    """Open an Atlas SQLite database, ensure the schema exists, run migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    migrate(conn)
    return conn
```

Add `from atlas.db.migrations import migrate` to imports. Delete `_repair_etf_score_schema`, `_widen_etf_holding_key`, and the module constants `ETF_HOLDING_COLUMNS`, `LEGACY_ETF_HOLDING_KEY`, `NULLABLE_ETF_SCORE_COLUMNS`, `ETF_HOLDING_REBUILD_DDL` (their long rationale comments move conceptually into `migrations.py`'s docstrings; do not paste them verbatim).

`load_seed_universe` body per fund becomes:

```python
        symbol = fund["symbol"]
        conn.execute(
            """
            INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'fund')
            ON CONFLICT(symbol) DO UPDATE SET name=excluded.name
            """,
            (symbol, fund["description"]),
        )
        conn.execute(
            """
            INSERT INTO fund (
                symbol, description, fund_type, category, select_list,
                gross_expense_ratio, information_technology_exposure, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                description=excluded.description,
                fund_type=excluded.fund_type,
                category=excluded.category,
                select_list=excluded.select_list,
                gross_expense_ratio=excluded.gross_expense_ratio,
                information_technology_exposure=excluded.information_technology_exposure,
                source=excluded.source
            """,
            (
                symbol,
                fund["description"],
                fund["fund_type"],
                fund["category"],
                fund["select_list"],
                fund["gross_expense_ratio"],
                fund["information_technology_exposure"],
                fund["source"],
            ),
        )
        conn.execute(
            "DELETE FROM fund_holding WHERE fund_symbol = ? AND source = 'seed_top_ten'",
            (symbol,),
        )
        for rank, holding_symbol in enumerate(fund["holding_symbols"], start=1):
            _ensure_holding_asset(conn, holding_symbol, None)
            conn.execute(
                """
                INSERT INTO fund_holding (fund_symbol, holding_symbol, rank, source)
                VALUES (?, ?, ?, 'seed_top_ten')
                ON CONFLICT(fund_symbol, holding_symbol, source) DO UPDATE SET
                    rank=excluded.rank
                WHERE fund_holding.source <> 'holdings_file'
                """,
                (symbol, holding_symbol, rank),
            )
        count += 1
```

The `fund["top_ten_holdings"]` raw string is no longer stored (drop it from the INSERT; `SeedUniverseProvider` still parses it into `holding_symbols` — do not change the provider). Preserve the existing comments about seed-row refresh and the upsert's conflict-target reasoning, updated to the new names.

New module-level helper (above `load_seed_universe`):

```python
def _ensure_holding_asset(
    conn: sqlite3.Connection, holding_symbol: str, holding_name: str | None
) -> None:
    """Ensure a held symbol exists in `asset`, as a company unless already a fund.

    `fund_holding.holding_symbol` references `asset(symbol)`: a fund's holding
    may be a company or another fund. An unknown symbol becomes a company stub;
    a symbol already registered (either type) is left exactly as it is.
    """
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'company') "
        "ON CONFLICT(symbol) DO NOTHING",
        (holding_symbol, holding_name),
    )
    conn.execute(
        "INSERT OR IGNORE INTO company (symbol) "
        "SELECT symbol FROM asset WHERE symbol = ? AND asset_type = 'company'",
        (holding_symbol,),
    )
```

`load_fund_holdings` becomes (docstring updated to the new table names, same content otherwise):

```python
def load_fund_holdings(conn: sqlite3.Connection, fund_symbol: str, path: Path) -> int:
    symbol = fund_symbol.strip().upper()
    holdings = sorted(HoldingsFileProvider(path).iter_holdings(), key=lambda h: h.weight, reverse=True)

    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, '', 'fund') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )
    conn.execute(
        "INSERT INTO fund (symbol, description) VALUES (?, '') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )
    conn.execute(
        "DELETE FROM fund_holding WHERE fund_symbol = ? AND source = 'holdings_file'",
        (symbol,),
    )
    for rank, holding in enumerate(holdings, start=1):
        _ensure_holding_asset(conn, holding.holding_symbol, holding.holding_name)
        conn.execute(
            """
            INSERT INTO fund_holding (
                fund_symbol, holding_symbol, holding_name, rank, weight, source
            ) VALUES (?, ?, ?, ?, ?, 'holdings_file')
            """,
            (symbol, holding.holding_symbol, holding.holding_name, rank, holding.weight),
        )
    conn.commit()
    return len(holdings)
```

(The parameter rename `etf_symbol` → `fund_symbol` is safe: the only caller, `cli/main.py`, passes it positionally.)

`forget_fund` core becomes (docstring updated; `ForgetFundResult` unchanged):

```python
    symbol = symbol.strip().upper()
    exists = conn.execute("SELECT 1 FROM fund WHERE symbol = ?", (symbol,)).fetchone()
    if exists is None:
        raise AtlasDataError(f"{symbol} is not in the universe. Nothing to forget.")

    holdings_removed = conn.execute(
        "DELETE FROM fund_holding WHERE fund_symbol = ?", (symbol,)
    ).rowcount
    score_removed = (
        conn.execute("DELETE FROM fund_score WHERE symbol = ?", (symbol,)).rowcount > 0
    )
    conn.execute("DELETE FROM fund WHERE symbol = ?", (symbol,))
    # The fund's own asset row goes too — unless another fund still holds this
    # symbol, in which case the FK from fund_holding.holding_symbol needs it.
    conn.execute(
        "DELETE FROM asset WHERE symbol = ? "
        "AND NOT EXISTS (SELECT 1 FROM fund_holding WHERE holding_symbol = ?)",
        (symbol, symbol),
    )
    portfolio_positions = int(
        conn.execute(
            "SELECT COUNT(*) AS c FROM portfolio_position WHERE symbol = ?", (symbol,)
        ).fetchone()["c"]
    )
    conn.commit()
```

- [ ] **Step 6: Re-point the four reader modules**

`src/atlas/scoring/engine.py` — three queries:

```python
# measured_diversification (line ~95):
        SELECT COUNT(*) AS holdings_count, COALESCE(SUM(weight), 0.0) AS weight_total
        FROM fund_holding
        WHERE fund_symbol = ? AND source = 'holdings_file'

# read_scores (line ~355): FROM etf_score  ->  FROM fund_score  (columns unchanged)

# score_all (line ~385):
    rows = conn.execute("SELECT * FROM fund ORDER BY symbol").fetchall()
# score_all upsert (line ~391): INSERT INTO fund_score (...) — table name only, columns unchanged.
```

(`score_etf` reads `row["symbol"]`, `description`, `category`, `gross_expense_ratio`, `information_technology_exposure` — all present on `fund`; no join needed. Update docstrings that name `etf`/`etf_score`.)

`src/atlas/analytics/overlap.py` — in `TOP_TEN_CTE`, rename `etf_holding` → `fund_holding` and every `etf_symbol` → `fund_symbol` (table references AND the CTE output columns), keeping CTE names `atlas_*` and output column set `(fund_symbol, holding_symbol, weight, source, top_rank)`. Update the two per-fund query filters (`WHERE fund_symbol = ?`) and `top_repeated_holdings`:

```python
        SELECT holding_symbol, COUNT(*) AS etf_count, GROUP_CONCAT(fund_symbol, ', ') AS etfs
        FROM atlas_top_ten
```

(The output aliases `etf_count`/`etfs` are consumed by `cli/main.py:148` and `web/app.py:253` — keep them.)

`src/atlas/portfolio/analysis.py` — `universe_coverage`: `FROM etf` → `FROM fund`, `etf_holding h` → `fund_holding h`, `h.etf_symbol` → `h.fund_symbol` (four queries, structure unchanged). `combined_concentration` weighted-holdings query:

```python
            "SELECT holding_symbol, weight FROM fund_holding "
            "WHERE fund_symbol = ? AND source = 'holdings_file' AND weight IS NOT NULL",
```

Update the docstrings/dataclass comments that name `etf_holding`.

`src/atlas/cli/main.py` — phantom-fund check (line ~203):

```python
        "SELECT 1 FROM fund WHERE symbol = ? AND source IS NOT NULL", (symbol,)
```

coverage total (line ~223):

```python
        "SELECT COALESCE(SUM(weight), 0) AS total FROM fund_holding "
        "WHERE fund_symbol = ? AND source = 'holdings_file'",
```

`src/atlas/web/app.py` — line 125: `SELECT COUNT(*) AS count FROM fund`; line 203: `SELECT * FROM fund WHERE symbol = ?` (the detail page reads `description`, `category`, `gross_expense_ratio`, `information_technology_exposure` — all on `fund`).

- [ ] **Step 7: Flip `tests/db_fixtures.py` to the new tables**

```python
def add_fund(conn, symbol, description="", *, fund_type=None, category=None,
             select_list=None, gross_expense_ratio=None,
             information_technology_exposure=None, source=None):
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'fund') "
        "ON CONFLICT(symbol) DO UPDATE SET name=excluded.name",
        (symbol, description),
    )
    conn.execute(
        """
        INSERT INTO fund (
            symbol, description, fund_type, category, select_list,
            gross_expense_ratio, information_technology_exposure, source
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(symbol) DO UPDATE SET
            description=excluded.description,
            fund_type=excluded.fund_type,
            category=excluded.category,
            select_list=excluded.select_list,
            gross_expense_ratio=excluded.gross_expense_ratio,
            information_technology_exposure=excluded.information_technology_exposure,
            source=excluded.source
        """,
        (symbol, description, fund_type, category, select_list,
         gross_expense_ratio, information_technology_exposure, source),
    )


def add_holding(conn, fund_symbol, holding_symbol, *, holding_name=None,
                rank=1, weight=None, source="seed_top_ten"):
    # Satisfy both FKs: the fund must exist, and the held symbol must be an
    # asset (company stub unless already registered).
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, '', 'fund') "
        "ON CONFLICT(symbol) DO NOTHING",
        (fund_symbol,),
    )
    conn.execute(
        "INSERT INTO fund (symbol, description) VALUES (?, '') "
        "ON CONFLICT(symbol) DO NOTHING",
        (fund_symbol,),
    )
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'company') "
        "ON CONFLICT(symbol) DO NOTHING",
        (holding_symbol, holding_name),
    )
    conn.execute(
        "INSERT OR IGNORE INTO company (symbol) "
        "SELECT symbol FROM asset WHERE symbol = ? AND asset_type = 'company'",
        (holding_symbol,),
    )
    conn.execute(
        """
        INSERT INTO fund_holding (
            fund_symbol, holding_symbol, holding_name, rank, weight, source
        ) VALUES (?, ?, ?, ?, ?, ?)
        """,
        (fund_symbol, holding_symbol, holding_name, rank, weight, source),
    )


def add_score(conn, symbol, *, role="Satellite", overall_score=None, ai_score=4,
              resilience_score=None, cost_score=None, diversification_score=None,
              explanation="test"):
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, '', 'fund') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )
    conn.execute(
        "INSERT INTO fund (symbol, description) VALUES (?, '') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )
    conn.execute(
        """
        INSERT INTO fund_score (
            symbol, role, overall_score, ai_score, resilience_score,
            cost_score, diversification_score, explanation
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (symbol, role, overall_score, ai_score, resilience_score,
         cost_score, diversification_score, explanation),
    )
```

- [ ] **Step 8: Delete the two superseded test files**

```bash
git rm tests/test_holding_key_migration.py tests/test_schema_repair.py
```

Their intent (legacy narrow-key and NOT-NULL shapes migrate safely; investor tables untouched; DDL drift guard) is restored as migration-input cases in Task 3.

- [ ] **Step 9: Sweep for stragglers**

Run: `grep -rn "etf_holding\|etf_score\|FROM etf\b\|INTO etf\b\|TABLE etf\b" src/ tests/`
Expected: hits only in `src/atlas/db/migrations.py` and `tests/test_migrations.py` (the legacy DDL and copy statements). Fix anything else — likely candidates: test assertions that SELECT from old tables directly, and docstrings (docstring renames are required too, but only code hits block the next step).

- [ ] **Step 10: Run the full suite**

Run: `uv run pytest`
Expected: PASS, including the Task-Step-1 migration tests. Investigate every failure — the usual causes are a missed query rename or a test asserting directly against an old table.

- [ ] **Step 11: Commit**

```bash
git add -A
git commit -m "feat: normalize universe schema (asset/fund/company/fund_holding) with versioned migration"
```

---

### Task 3: Migration edge-case and runner tests

Restores the deleted files' coverage against the new runner, plus the spec's remaining migration requirements. Pure test additions — expected to pass against Task 2's implementation; any failure is a Task 2 bug to fix here.

**Files:**
- Modify: `tests/test_migrations.py`

**Interfaces:**
- Consumes: `connect`, `migrate`, `LATEST_VERSION`, `make_legacy_db`, `LEGACY_SCHEMA`, `table_names` from Task 2.
- Produces: nothing new.

- [ ] **Step 1: Add the edge-case tests**

Add to `tests/test_migrations.py`. For `LEGACY_NARROW_KEY_SCHEMA`, copy the `LEGACY_SCHEMA` string from the deleted `tests/test_holding_key_migration.py` (retrieve with `git show HEAD~1:tests/test_holding_key_migration.py`); for the NOT-NULL `etf_score` DDL, copy `_make_legacy_database`'s DDL from the deleted `tests/test_schema_repair.py` the same way.

```python
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
    # Build with the NOT-NULL etf_score DDL from deleted test_schema_repair.py,
    # insert a fully-populated score row, connect, assert the row is in
    # fund_score unchanged and PRAGMA table_info(fund_score) shows
    # overall_score/resilience_score/cost_score/diversification_score nullable.


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
    # In make_legacy_db-style setup, also insert one portfolio, one position,
    # one journal entry (copy the INSERT statements from the deleted
    # test_schema_repair.py's _make_legacy_database). After connect(), select
    # each row and assert every column value is exactly what was inserted.


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
```

Fill in the two comment-bodied tests with real code following their docstrings; every assertion named in the comments is required.

- [ ] **Step 2: Run them**

Run: `uv run pytest tests/test_migrations.py -v`
Expected: PASS. A failure here is a genuine Task 2 defect — fix it in `src/atlas/db/migrations.py` and note the fix in the commit message.

- [ ] **Step 3: Run the full suite, then commit**

Run: `uv run pytest`

```bash
git add tests/test_migrations.py src/atlas/db/migrations.py
git commit -m "test: cover migration edge cases and runner rollback"
```

---

### Task 4: Type-aware import behaviors

Three behaviors the normalized model newly makes possible. Strict TDD: each gets a failing test first.

**Files:**
- Modify: `src/atlas/db/database.py`
- Create: `tests/test_asset_types.py`

**Interfaces:**
- Consumes: Task 2's `load_seed_universe`, `load_fund_holdings`, `forget_fund`, `_ensure_holding_asset`; Task 1's fixtures.
- Produces: `load_fund_holdings` raises `AtlasDataError` for a company-typed symbol; seed import promotes company→fund; `forget_fund` garbage-collects orphaned company stubs.

- [ ] **Step 1: Failing test — seed import promotes a company stub to a fund**

```python
from __future__ import annotations

import pytest

from atlas.db.database import connect, forget_fund, load_fund_holdings, load_seed_universe
from atlas.exceptions import AtlasDataError

SEED_HEADER = (
    "Symbol,Description,Fund Type,ETF Select List® Category,ETF Select List,"
    "Top Ten Holdings,Gross Expense Ratio,Sector Exposure: Information Technology,Source\n"
)


def write_seed_csv(tmp_path, *rows: str):
    """One seed row per string, matching data/atlas_seed_universe.csv's columns."""
    path = tmp_path / "seed.csv"
    path.write_text(SEED_HEADER + "".join(row + "\n" for row in rows), encoding="utf-8")
    return path


def write_holdings_csv(tmp_path, name: str, *rows: tuple[str, str, float]):
    """(ticker, holding_name, weight_percent) rows in an issuer-file shape."""
    path = tmp_path / name
    lines = ["Ticker,Name,Weight\n"]
    lines += [f"{ticker},{holding_name},{weight}\n" for ticker, holding_name, weight in rows]
    path.write_text("".join(lines), encoding="utf-8")
    return path


def test_seed_import_promotes_held_symbol_to_fund(tmp_path):
    conn = connect(tmp_path / "atlas.db")
    # 1. Import holdings for SOMEFUND whose file names VTI -> VTI becomes a company stub.
    load_fund_holdings(
        conn, "SOMEFUND", write_holdings_csv(tmp_path, "somefund.csv", ("VTI", "Vanguard Total", 12.0))
    )
    assert conn.execute("SELECT asset_type FROM asset WHERE symbol='VTI'").fetchone()[0] == "company"
    # 2. Seed CSV listing VTI as a fund arrives.
    load_seed_universe(
        conn,
        write_seed_csv(tmp_path, "VTI,Vanguard Total Stock Market ETF,ETF,Large Blend,Yes,--,0.03%,--,Seed"),
    )
    assert conn.execute("SELECT asset_type FROM asset WHERE symbol='VTI'").fetchone()[0] == "fund"
    assert conn.execute("SELECT 1 FROM company WHERE symbol='VTI'").fetchone() is None
    assert conn.execute("SELECT 1 FROM fund WHERE symbol='VTI'").fetchone()
    # SOMEFUND's holding row referencing VTI survives the promotion.
    assert conn.execute(
        "SELECT 1 FROM fund_holding WHERE fund_symbol='SOMEFUND' AND holding_symbol='VTI'"
    ).fetchone()
```

Run: `uv run pytest tests/test_asset_types.py -v` — expected FAIL (asset_type stays 'company').

- [ ] **Step 2: Implement promotion in `load_seed_universe`**

Change the asset upsert to:

```python
        conn.execute(
            """
            INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'fund')
            ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, asset_type='fund'
            """,
            (symbol, fund["description"]),
        )
        # A symbol previously known only as some fund's holding was a company
        # stub; the seed CSV saying it is a fund is better evidence. Promote:
        # the company row goes, existing fund_holding rows that reference the
        # symbol keep working because their FK targets asset, not company.
        conn.execute("DELETE FROM company WHERE symbol = ?", (symbol,))
```

Run the test — PASS.

- [ ] **Step 3: Failing test — importing holdings for a company-typed symbol refuses**

```python
def test_import_holdings_for_company_symbol_refuses(tmp_path):
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(
        conn, "SOMEFUND", write_holdings_csv(tmp_path, "somefund.csv", ("NVDA", "NVIDIA Corp", 7.5))
    )  # NVDA -> company stub
    with pytest.raises(AtlasDataError, match="NVDA"):
        load_fund_holdings(
            conn, "NVDA", write_holdings_csv(tmp_path, "nvda.csv", ("AAPL", "Apple Inc", 3.0))
        )
    # Nothing was written for NVDA-as-fund.
    assert conn.execute("SELECT 1 FROM fund WHERE symbol='NVDA'").fetchone() is None
    assert conn.execute(
        "SELECT COUNT(*) FROM fund_holding WHERE fund_symbol='NVDA'"
    ).fetchone()[0] == 0
```

Expected FAIL: no error raised (the asset insert no-ops and a `fund` row appears).

- [ ] **Step 4: Implement the refusal in `load_fund_holdings`**

After computing `symbol`, before any write:

```python
    existing = conn.execute(
        "SELECT asset_type FROM asset WHERE symbol = ?", (symbol,)
    ).fetchone()
    if existing is not None and existing["asset_type"] == "company":
        raise AtlasDataError(
            f"{symbol} is registered as a company (a holding of other funds), "
            "not a fund. Not importing a holdings file for it."
        )
```

Run the test — PASS.

- [ ] **Step 5: Failing test — forget-fund garbage-collects orphaned company stubs**

```python
def test_forget_fund_removes_orphaned_company_stubs(tmp_path):
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(
        conn, "FUNDA", write_holdings_csv(tmp_path, "funda.csv", ("ZZZQ", "Exclusive Co", 4.0))
    )  # ZZZQ held only by FUNDA
    load_fund_holdings(
        conn, "FUNDB", write_holdings_csv(tmp_path, "fundb.csv", ("MSFT", "Microsoft", 6.0))
    )  # MSFT held by FUNDB too
    conn.execute(  # FUNDA also holds MSFT so MSFT is shared
        "INSERT INTO fund_holding (fund_symbol, holding_symbol, rank, weight, source)"
        " VALUES ('FUNDA', 'MSFT', 2, 1.0, 'holdings_file')"
    )
    forget_fund(conn, "FUNDA")
    # FUNDA and its exclusive stub are gone entirely...
    assert conn.execute("SELECT 1 FROM asset WHERE symbol='FUNDA'").fetchone() is None
    assert conn.execute("SELECT 1 FROM asset WHERE symbol='ZZZQ'").fetchone() is None
    assert conn.execute("SELECT 1 FROM company WHERE symbol='ZZZQ'").fetchone() is None
    # ...the shared stub survives because FUNDB still holds it.
    assert conn.execute("SELECT 1 FROM asset WHERE symbol='MSFT'").fetchone()
```

(Adjust the shared-holding insert if `_ensure_holding_asset` is needed first — MSFT already exists from FUNDB's import, so the raw insert is FK-clean.)

Expected FAIL: ZZZQ's asset/company rows survive.

- [ ] **Step 6: Implement stub GC in `forget_fund`**

After the fund's own asset delete, before the `portfolio_positions` count:

```python
    # Company stubs exist only as anchors for fund_holding rows. Any stub no
    # fund holds any more is residue of the import being undone; sweep it.
    conn.execute(
        "DELETE FROM company WHERE symbol NOT IN (SELECT holding_symbol FROM fund_holding)"
    )
    conn.execute(
        "DELETE FROM asset WHERE asset_type = 'company' "
        "AND symbol NOT IN (SELECT symbol FROM company) "
        "AND symbol NOT IN (SELECT holding_symbol FROM fund_holding)"
    )
```

Run the test — PASS.

- [ ] **Step 7: Full suite, commit**

Run: `uv run pytest`

```bash
git add src/atlas/db/database.py tests/test_asset_types.py
git commit -m "feat: type-aware asset registry — promotion, import refusal, stub GC"
```

---

### Task 5: Documentation and milestone close-out

**Files:**
- Modify: `CLAUDE.md` (project one)
- Modify: `docs/foundation/ROADMAP_FOUNDATION_PHASE.md`
- Create: `docs/ATLAS_v0_8_NOTES.md`

**Interfaces:** none — prose only.

- [ ] **Step 1: Update `CLAUDE.md`**

In the "Investment / domain layer" section, rewrite the `db/database.py + db/schema.sql` bullet to describe: the normalized tables (`asset` supertype; `fund`/`company` subtypes; `fund_holding` keyed by `(fund_symbol, holding_symbol, source)`; `fund_score`; empty `theme`), and the `PRAGMA user_version` migration runner in `db/migrations.py` (replacing the sentence about idempotent `CREATE TABLE IF NOT EXISTS` being the whole story). Update any other `etf_holding`/`etf_score` mention in the file (the scoring bullet names `etf_score`).

- [ ] **Step 2: Mark the roadmap milestone delivered**

In `docs/foundation/ROADMAP_FOUNDATION_PHASE.md` change the v0.8 heading to `## v0.8 — Normalized Schema (delivered)`.

- [ ] **Step 3: Write `docs/ATLAS_v0_8_NOTES.md`**

Follow the structure of `docs/ATLAS_v0_7_NOTES.md` (read it first). Cover: the new tables, the migration runner and why the two ad-hoc repairs were retired, the full-cutover decision, the three type-aware behaviors from Task 4, and what deliberately did not change (CLI surface, scoring logic, NULL semantics, investor tables). Link the spec and this plan.

- [ ] **Step 4: Full suite one last time, commit**

Run: `uv run pytest`

```bash
git add CLAUDE.md docs/
git commit -m "docs: record v0.8 normalized schema milestone"
```
