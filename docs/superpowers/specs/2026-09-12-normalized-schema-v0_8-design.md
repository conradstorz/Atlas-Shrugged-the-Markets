# v0.8 Normalized Schema — Design

Date: 2026-09-12
Status: approved
Roadmap milestone: v0.8 — Normalized Schema (`docs/foundation/ROADMAP_FOUNDATION_PHASE.md`)

## Goal

Replace the prototype `etf` / `etf_holding` / `etf_score` tables with the
normalized entity model from `docs/foundation/DATA_MODEL_v0_6.md`, migrate
existing databases in place, and keep every CLI command, flag, and output
format working unchanged.

## Scope

In scope: `asset`, `fund`, `company`, `theme`, `fund_holding` tables; a
versioned migration mechanism; full cutover of all readers and writers;
renaming `etf_score` to `fund_score`.

Out of scope (later milestones): `sector`, `theme_link`, `price_history`,
`fund_metadata_snapshot`; populating `theme` (v0.9); the Scoring/Model-zone
tables (`score_model`, `score_result`, …); any FK from `portfolio_position`
or the decision journal to `asset` — their `symbol` columns stay free text.

## Decisions made

1. **Scope**: roadmap's four tables plus `fund_holding` — the tables current
   code has data for. Empty-forever tables wait for the milestone that feeds
   them.
2. **Cutover**: full cutover in v0.8. One-time data migration, then all
   modules read/write only the new tables; old tables are dropped. No
   dual-write, no compatibility views.
3. **Migration mechanism**: `PRAGMA user_version`-based numbered steps,
   replacing the two ad-hoc introspection repairs in `connect()`.
4. **Entity shape**: asset as supertype. `fund` and `company` are subtype
   tables keyed by the same symbol with a FK to `asset`.

## Schema

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
    source                  TEXT               -- NULL = stub created by import-holdings; the CLI phantom-fund warning keys off this, as today
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
    weight          REAL,                      -- percent of fund, e.g. 6.83 = 6.83%; NULL for seed select-list rows
    source          TEXT NOT NULL DEFAULT 'seed_top_ten',
    -- source stays part of the key so a fund's seed select-list row and its
    -- imported holdings-file row for the same company coexist (see the
    -- rationale comment on the old etf_holding table / ADR history).
    PRIMARY KEY (fund_symbol, holding_symbol, source)
);

CREATE TABLE IF NOT EXISTS fund_score (
    symbol TEXT PRIMARY KEY REFERENCES fund(symbol),
    role TEXT NOT NULL,
    overall_score INTEGER,
    ai_score INTEGER NOT NULL,
    resilience_score INTEGER,
    cost_score INTEGER,
    diversification_score INTEGER,
    explanation TEXT NOT NULL
    -- identical columns and nullability semantics to the old etf_score;
    -- NULL still means "not measured, excluded", never a default
);
```

Notes:

- `etf.top_ten_holdings` (the raw pipe-delimited string) is **not** carried
  into `fund`. It is parsed into holdings rows at import time; the migration
  re-derives nothing from it.
- `fund_holding.holding_symbol` references `asset`, not `company`, because a
  fund can hold another fund.
- Dropped after migration: `etf`, `etf_holding`, `etf_score`.

## Migration mechanism

`connect()` gains a versioned migration runner replacing the two ad-hoc
repairs (`_repair_etf_score_schema`, `_widen_etf_holding_key`), which are
deleted:

- Read `PRAGMA user_version`.
- For each numbered step above the current version, in order: run the step
  inside one transaction (`PRAGMA foreign_keys` saved/OFF/restored around it,
  as the existing rebuild does), set `user_version` on success.
- On any failure: roll back, raise `AtlasError` naming the step. The database
  is left at its prior version and remains usable by the previous binary.

Steps:

1. **Step 1** — the old `etf_score` nullability repair (detects `notnull` on
   the nullable score columns, rebuilds if found; no-op otherwise).
2. **Step 2** — the old `etf_holding` PK widening (fires only on the exact
   legacy two-column key; no-op otherwise).
3. **Step 3** — v0.8 normalization:
   1. Create the new tables (they are also in `schema.sql` for fresh DBs).
   2. Each `etf` row → `asset(symbol, description AS name, 'fund')` +
      `fund(...)` carrying all columns except `top_ten_holdings`.
   3. Each distinct `etf_holding.holding_symbol` not already an asset →
      stub `asset(symbol, NULL or holding_name, 'company')` + `company` row.
      Symbols that already exist as funds are left as funds (no `company`
      row).
   4. `etf_holding` → `fund_holding` verbatim. Guards as in the existing
      rebuild: row-count assertion before drop and after copy, plus
      `PRAGMA foreign_key_check` orphan comparison.
   5. `etf_score` → `fund_score` verbatim.
   6. Drop `etf_holding`, then `etf_score`, then `etf` (FK order).

Fresh databases: `schema.sql` creates only the new tables. The runner detects
a fresh DB (no `etf` table and version 0) and sets `user_version` straight to
the latest without running steps.

## Code cutover

SQL-only changes; command names, flags, dataclasses, and output formats stay
identical — that is the backward compatibility the roadmap requires.

- `db/database.py` — seed loader writes `asset` + `fund` + `fund_holding`
  (upsert semantics preserved, including the `holdings_file`-wins guard on
  rank updates). Holdings import writes `fund_holding` plus stub
  `asset`/`company` rows for unknown holdings and a stub `asset`+`fund` row
  for an unknown fund symbol (source NULL, as today). `forget_fund` deletes
  across `fund_holding`, `fund_score`, `fund`, then `company` if the symbol
  has no remaining references, then `asset`.
- `scoring/engine.py` — iterates `fund` (join `asset` where a name is
  needed), writes `fund_score`; diversification query targets `fund_holding`
  filtered `source='holdings_file'`, unchanged logic.
- `analytics/overlap.py` — `TOP_TEN_CTE` re-pointed at `fund_holding`
  (column renames only; the single-source rule is unchanged).
- `portfolio/analysis.py` — coverage counts and look-through queries renamed
  to `fund` / `fund_holding`.
- `cli/main.py` — phantom-fund warning reads `fund.source IS NOT NULL`;
  coverage `SUM(weight)` reads `fund_holding`.
- `web/app.py` — universe count and detail page read `fund` join `asset`.

## Error handling

- Migration failure is atomic per step: rollback, `AtlasError` naming the
  failing step, database untouched at its prior `user_version`.
- Holdings import of a symbol that exists as `asset_type='company'` being
  imported as a fund: promote is out of scope; the import creates the stub
  `fund` row only when the symbol is absent, mirroring today's
  `ON CONFLICT DO NOTHING`. A company-typed symbol used as a fund raises the
  same `AtlasError` path as any FK violation, with a message naming the
  symbol.

## Testing

- Existing suites keep passing with fixture INSERTs rewritten to the new
  tables (43 `INSERT INTO etf*` sites across 11 test files).
- New migration tests, following the `test_holding_key_migration.py`
  pattern (hand-written legacy DDL applied via raw sqlite3, then
  `connect()`):
  - data fidelity: every `etf`/`etf_holding`/`etf_score` row appears in the
    new tables with identical values;
  - stub-asset creation for held-only symbols, including a fund held by
    another fund (no spurious `company` row);
  - drift guard: migrated table shapes match freshly created ones
    (PRAGMA comparison);
  - a v0.5-era database (pre-both-repairs) upgrades through steps 1–3 in a
    single open;
  - investor-entered tables (`portfolio*`, `decision_journal_entry`)
    untouched byte-for-byte.
- Migration-runner tests: fresh-DB fast path sets latest version without
  running steps; a step that raises mid-way rolls back and leaves
  `user_version` at the prior value.
- Old repair-function tests (`test_schema_repair.py`,
  `test_holding_key_migration.py`) are repointed at the runner steps.
