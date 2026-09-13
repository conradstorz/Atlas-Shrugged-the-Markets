# Atlas v0.8 Notes

Atlas v0.8 replaces the prototype `etf`/`etf_holding`/`etf_score` tables with a normalized
schema — `asset`/`fund`/`company`/`theme`/`fund_holding`/`fund_score` — migrating existing
databases in place, with every CLI command's behavior and output unchanged.

## The problem this milestone fixed

The prototype schema had one table, `etf`, standing in for two different kinds of thing:
funds Atlas scores, and the companies those funds hold. A holding's symbol was just a text
column on `etf_holding`, with no row of its own and no way to record that the same symbol
might itself be a fund elsewhere in the universe. There was also nowhere for v0.9's theme
taxonomy to attach. The normalized schema gives every symbol one supertype row (`asset`),
lets it carry a `fund` row, a `company` row, or both, and gives `fund_holding` a real foreign
key to whichever it points at.

## New tables

- `asset(symbol, name, asset_type)` — supertype registry for every symbol Atlas knows about;
  `asset_type` is `'fund'` or `'company'`.
- `fund(symbol, ...)` — subtype table keyed by the same symbol as `asset`; holds the columns
  the old `etf` table had (description, fund_type, category, select_list, expense ratio, IT
  exposure, source).
- `company(symbol)` — subtype table with no attributes yet; exists purely as an anchor for
  v0.9's themes and sector data.
- `fund_holding(fund_symbol, holding_symbol, holding_name, rank, weight, source)` — primary
  key `(fund_symbol, holding_symbol, source)`, with foreign keys to `fund(symbol)` and
  `asset(symbol)`. The wider key (`source` included) lets a fund's seed top-ten membership row
  and its imported holdings-file row for the same company coexist.
- `fund_score` — same columns and nullability as the old `etf_score`; `overall_score`,
  `resilience_score`, `cost_score`, and `diversification_score` stay nullable, `role` and
  `ai_score` stay `NOT NULL`.
- `theme` — created empty, awaiting v0.9's economic theme taxonomy.

The old `etf`, `etf_holding`, and `etf_score` tables are dropped by the migration below.

## The migration runner

`src/atlas/db/migrations.py` adds a `PRAGMA user_version` migration runner (`LATEST_VERSION =
1`), called by `connect()` right after `schema.sql`. It replaces the two ad-hoc introspection
repairs the prototype schema had accumulated (`_repair_etf_score_schema`,
`_widen_etf_holding_key`) with one versioned step, `_normalize_universe`. A fresh database is
stamped at `LATEST_VERSION` without running any step; an existing database with prototype data
runs the step once and is stamped afterward.

The step is atomic: it turns foreign keys off for the duration (SQLite disallows altering the
tables a live FK references), runs inside one transaction, copies rows by column name into the
new tables, and checks row counts and `PRAGMA foreign_key_check` on every new table before
dropping anything old. Any failure — a count mismatch, an orphaned reference — rolls the whole
step back, raises `AtlasError`, and leaves `user_version` unchanged, so the database stays
usable by the previous binary. Holdings rows that referenced a fund symbol with no matching
`etf` row (a pre-existing orphan) become stub funds during the copy rather than being dropped
— they are the investor's data, not an invariant to enforce away.

Investor tables (`portfolio`, `portfolio_position`, `decision_journal_entry`) are never
touched by the migration; this is tested to be byte-identical before and after.

### Deviation from the spec

The spec (`docs/superpowers/specs/2026-09-12-normalized-schema-v0_8-design.md`) proposed
folding the two retired repairs in as migration steps 1 and 2, ahead of the normalization
step. That can't work as written: `_repair_etf_score_schema` re-ran `schema.sql` to fix up
`etf_score`'s columns, and `schema.sql` no longer contains `etf_score` at all after this
change. Both repairs are also subsumed by the normalization step itself, which copies by
column name into fresh tables that already have the wide `fund_holding` key and nullable
`fund_score` columns — there is nothing left for either repair to do. The runner therefore
ships with a single step, `user_version` 0→1. The old repairs' test intent (legacy narrow-key
`etf_holding`, legacy `NOT NULL` `etf_score`) is preserved as migration-input test cases
instead of as separate steps. See the plan
(`docs/superpowers/plans/2026-09-12-normalized-schema-v0_8.md`) header for the full rationale.

## Type-aware behaviors

Three behaviors were added or tightened so the fund/company split holds up under real usage,
not just under migration:

- **Seed import promotes a company stub to a fund.** If a symbol was previously known only as
  a holding of some other fund (a `company` stub), and the seed universe CSV says it is itself
  a fund, the seed CSV is treated as the better evidence: the `company` row is deleted and a
  `fund` row is inserted. Existing `fund_holding` rows that reference the symbol keep working,
  since their foreign key targets `asset`, not `company`.
- **`import-holdings` refuses a company-typed symbol.** Before writing anything,
  `load_fund_holdings` checks whether the symbol is already registered with
  `asset_type = 'company'` and, if so, raises `AtlasDataError` rather than letting a company
  quietly acquire a `fund` row from a holdings-file import.
- **`forget_fund` deletes a dual-registered symbol's `company` row before its `asset` row**,
  and garbage-collects orphaned `company` stubs left behind. A symbol can be dual-registered —
  a `company` stub from being named as a holding, plus its own `fund` row from having holdings
  imported for it — and `company.symbol` references `asset(symbol)`, so the child row has to go
  first. Both the deletion and the stub sweep exclude any symbol still referenced by a
  `fund_holding` row or still present in `fund`, so a symbol still in active use is never swept
  away as if it were residue.

## What deliberately did not change

- CLI command surface, flags, and printed output.
- Scoring logic and `SCORER_VERSION` (`scoring/model.py`) — the scorer still reads from
  `fund`/`fund_holding` conceptually the same way it read `etf`/`etf_holding`.
- NULL-score semantics: NULL still means "not measured," never a default; 0 is still a real
  score.
- `weight` semantics: percent of fund (6.83 means 6.83%), NULL for seed rows with membership
  only.
- Investor tables (`portfolio`, `portfolio_position`, `decision_journal_entry`) and their
  contents.
- Providers' parsers (`providers/seed_universe.py`, `providers/portfolio_files.py`,
  `providers/holdings_file.py`).

201 tests pass. Test fixtures for the universe tables now go through `tests/db_fixtures.py`
so a future schema change touches one helper module instead of every insert site.

## References

- Spec: `docs/superpowers/specs/2026-09-12-normalized-schema-v0_8-design.md`
- Plan: `docs/superpowers/plans/2026-09-12-normalized-schema-v0_8.md`
