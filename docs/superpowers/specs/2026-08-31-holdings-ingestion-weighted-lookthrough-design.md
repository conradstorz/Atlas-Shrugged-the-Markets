# Holdings Ingestion + Weighted Look-Through — Design

Date: 2026-08-31
Status: Approved (pending spec review)

## Overview

Atlas currently estimates fund look-through by distributing **100% of a fund's
market value equally across its parsed top-ten holdings**. Because the seed
select-list CSV carries only holding *symbols* (`|NVDA||AAPL|`) and no weights,
this is not a rough estimate — it is a claim the data cannot support.

Concretely, on `examples/sample_portfolio.csv` today:

```
SCHB (Schwab U.S. Broad Market, ~2,500 stocks), $50,000 position
  -> Atlas reports NVDA at 5.00% / $5,000
```

SCHB's top ten is roughly a third of the fund. The other ~2,490 names report as
0%. Per-name figures are overstated (severely for the 8th-10th holdings) and the
tail is invisible. This is the single defect standing between the concentration
engine and a number worth acting on.

This work adds real weighted holdings ingestion and changes the engine to assert
only what its data supports.

## Goals

- Ingest issuer fund-holdings CSVs (with weights) into `etf_holding.weight`.
- Look through funds using **exact weights** where available.
- For a fund with no weights, report its value as **unmodeled** rather than
  fabricating an equal-weight distribution.
- Make coverage a first-class, visible output at both universe and portfolio
  level, so the user always knows what fraction of their money the table
  describes.
- Prove `providers/base.py` by implementing it, rather than deleting it unused.

## Non-Goals (YAGNI)

- Any external/network data fetch. Files are downloaded by hand; Atlas stays
  local-first (Constitution Article II).
- Holdings history, as-of dating, or point-in-time reconstruction. A fund's
  holdings are a single current snapshot; re-import replaces.
- Second-order look-through (a fund holding another fund).
- The normalized `asset`/`fund`/`company`/`theme` schema. That is v0.8 and gets
  its own spec.
- Reviving `core/` (scoring, decisions, evidence, themes) or `models/domain.py`.
  Those map to later milestones and stay dead for now.
- Auto-detecting which fund a holdings file belongs to. The fund symbol is an
  explicit CLI argument.

## Input Format

Issuer holdings exports vary in header wording but share a shape. Real examples:

```
iShares:   Ticker, Name, Sector, Asset Class, Weight (%), ...
Schwab:    Symbol, Description, % of Assets, ...
Invesco:   Holding Ticker, Name, Weight, ...
Vanguard:  Ticker, Holdings, % of funds, ...
```

Characteristics the parser must handle:

- Issuer preamble lines (fund name, as-of date, disclaimers) before the header.
- Header located by content, not row index: the first row containing **both** a
  symbol-like and a weight-like column.
- Weights formatted `6.83`, `6.83%`, or `"6.83"`; thousands separators in other
  columns.
- Non-equity rows (cash, futures, FX, "Other") whose symbol cell is blank,
  `--`, or `N/A`.
- Trailing total rows.
- Duplicate symbols (multiple listings or share classes) within one file.

### Column matching

Case-insensitive substring match, first hit wins, mirroring `schwab.py::_column`:

- symbol: `ticker`, `symbol`, `holding`
- name: `name`, `description`, `holdings`, `security`
- weight: `weight`, `% of net assets`, `% of assets`, `% of funds`,
  `portfolio weight`, `allocation`

## Data Model

`etf_holding.weight` already exists (`REAL`, nullable) and is never populated
today. **No migration is required.** The `source` column distinguishes the two
kinds of row:

| `source`        | `weight`           | Meaning                           | Consumed by                                           |
| --------------- | ------------------ | --------------------------------- | ----------------------------------------------------- |
| `seed_top_ten`  | `NULL`             | membership only, from select-list | `compare-overlap`, `repeat-holdings`, diversification |
| `holdings_file` | percent, e.g. 6.83 | real weight from an issuer file   | **dollar look-through**                               |

Weights are stored **as percent** (matching every issuer file), documented on
the column in `schema.sql`.

### Seed loader must not clobber imported holdings

`generate-report` and `web/app.py::_ensure_initialized` both call
`load_seed_universe` on every invocation. It currently deletes and re-inserts
`seed_top_ten` rows with
`ON CONFLICT(etf_symbol, holding_symbol) DO UPDATE SET rank, source`, which
would flip an imported `holdings_file` row back to `seed_top_ten` on the next
`atlas serve`, silently destroying real data while leaving a stale weight
attached to a row now labelled as seed data.

**Rule: a fund with any `holdings_file` rows is skipped entirely by the seed
loader's holdings parsing.** Its `etf` metadata row still updates. Real data
outranks seed data permanently; the only way to replace imported holdings is to
re-import them.

## Component Design

### 1. Provider interfaces — `src/atlas/providers/base.py`

Existing interfaces are kept and implemented. One is added, because holdings do
not fit `ResearchDataProvider.iter_funds()` ("yield public fund metadata
records") and forcing them through it would be pretend-reuse:

```python
@dataclass(frozen=True)
class FundHolding:
    holding_symbol: str
    holding_name: str | None
    weight: float          # percent, e.g. 6.83


class FundHoldingsProvider(ABC):
    """Interface for a source of one fund's holdings with weights."""

    @abstractmethod
    def iter_holdings(self) -> Iterable[FundHolding]:
        """Yield the fund's holdings."""
```

Providers are **pure parsers**: they read a file and yield records. They take no
`sqlite3.Connection` and perform no writes. Persistence stays in `db/` and the
feature modules. This keeps them unit-testable without a database and keeps the
Kernel boundary (ADR-0002) intact.

Resulting wiring — every interface in `providers/base.py` becomes live. All
provider *classes* live under `providers/`; the existing `load_*` functions
remain where they are and become thin persistence wrappers that consume a
provider:

| Interface                             | Implementation           | Module                            | Persistence caller                  |
| ------------------------------------- | ------------------------ | --------------------------------- | ----------------------------------- |
| `ResearchDataProvider.iter_funds()`   | `SeedUniverseProvider`   | `providers/seed_universe.py`      | `db.load_seed_universe`             |
| `FundHoldingsProvider.iter_holdings()`| `HoldingsFileProvider`   | `providers/holdings_file.py`      | `db.load_fund_holdings`             |
| `PortfolioImportProvider.import_file()`| `SchwabPositionsProvider`| `providers/portfolio_files.py`    | `portfolio.schwab.load_schwab_positions` |
| `PortfolioImportProvider.import_file()`| `PortfolioCsvProvider`   | `providers/portfolio_files.py`    | `db.load_portfolio_csv`             |

### 1a. Shared parsing helpers — `src/atlas/parsing.py` (new)

Providers must not import from `db/`, or the "pure parser" boundary above is
fiction on its first commit. But the helpers they need (`parse_money`,
`normalize_asset_type`) currently live in `db/database.py`, and
`scoring/engine.py` carries its own private near-duplicate `_parse_percent`.

Move the format-parsing helpers to a dependency-free `atlas/parsing.py`:
`parse_money`, `parse_percent`, `normalize_asset_type`. `db/database.py`,
`portfolio/schwab.py`, `scoring/engine.py`, and the new providers all import
from there. `tests/test_parsing.py` updates its import accordingly.

This is a move, not a rewrite — the function bodies are unchanged apart from
`scoring/engine.py` losing its private copy.

### 2. Holdings parser — `src/atlas/providers/holdings_file.py` (new)

```
class HoldingsFileProvider(FundHoldingsProvider):
    def __init__(self, path: Path) -> None
    def iter_holdings(self) -> Iterable[FundHolding]
```

Behaviour:

- Locate the header row by content (see Input Format).
- Skip rows whose symbol cell is empty, `--`, or `N/A`. Their weight is
  therefore **not** counted toward modeled share, correctly leaving a fund's
  cash/derivative sleeve unmodeled rather than misattributed.
- Skip rows whose first cell begins with `total`.
- Parse weight via a shared `parse_percent` helper (strip `%`, commas,
  whitespace). A row whose weight will not parse is skipped.
- Sum duplicate symbols within one file.
- Negative weights are preserved, not filtered. Atlas does not editorialize
  source data (same stance as the Schwab spec).

### 3. Fractions-vs-percent guard

A file expressing weights as fractions (`0.0683`) instead of percent (`6.83`)
would import silently and understate every exposure by 100x. This is the most
dangerous realistic failure mode, so it fails loudly:

- If the parsed rows total `<= 1.5` with more than 5 rows present, raise
  `AtlasDataError` naming the file and the computed total, instructing the user
  to convert to percent.
- If the parsed rows total `> 100.5`, raise `AtlasDataError` — the file is
  malformed or the wrong column matched.

`AtlasDataError(AtlasError)` is added to `exceptions.py` alongside the existing
configuration/secret/plugin errors.

### 4. Persistence — `src/atlas/db/database.py`

```
load_fund_holdings(conn, etf_symbol: str, path: Path) -> int
```

Deletes **all** existing `etf_holding` rows for the fund (both sources), then
inserts the parsed rows with `source='holdings_file'`, `rank` by descending
weight. Returns the number of holdings stored. Re-import fully replaces.

### 5. Concentration engine — `src/atlas/portfolio/analysis.py`

`combined_concentration` changes:

- **Direct `equity`** — full market value. Exact. Unchanged.
- **Fund with `holdings_file` rows** — each holding receives
  `market_value * weight / 100`. Modeled share is `SUM(weight) / 100`; the
  remainder `market_value * (1 - modeled_share)` goes to
  `unmodeled_fund_value`.
- **Fund without weights** — the entire market value goes to
  `unmodeled_fund_value`. **No equal-weight estimate is produced.**

New/updated result types:

```python
@dataclass(frozen=True)
class FundCoverage:
    symbol: str
    market_value: float
    has_weights: bool
    modeled_share: float     # 0.0 - 1.0
    modeled_value: float


@dataclass(frozen=True)
class ConcentrationReport:
    lines: list[ConcentrationLine]
    total_value: float
    modeled_value: float
    unmodeled_fund_value: float
    cash_value: float
    other_value: float
    fund_coverage: list[FundCoverage]
```

**Accounting invariant**, asserted by test:

```
total_value == modeled_value + unmodeled_fund_value + cash_value + other_value
```

This also closes an existing gap: positions with `asset_type='other'` currently
dilute the denominator while appearing nowhere in the output. They are now
reported explicitly as `other_value`.

`portfolio_hidden_concentration` (the older v0.3 function, already off the
CLI/report path but retained for its tests) is **removed** in this pass. It is
the same unsupported equal-weight math and keeping it invites reuse.

### 6. CLI + report surfacing — `cli/main.py`, `reports/markdown.py`

New commands:

```
atlas import-holdings SYMBOL FILE [--db]
atlas coverage [--name PORTFOLIO] [--db]
```

- `import-holdings` prints stored count and the file's total weight, e.g.
  `Imported 10 holdings for SCHB (33.61% of fund by weight).`
- `coverage` reports **universe** coverage (funds with weights / with
  membership only / total) and, when `--name` is given, **portfolio** coverage
  (modeled share of dollars, plus per-fund lines).
- `analyze-portfolio` prints a coverage line above the table:
  `Modeled: $19,000.00 of $100,000.00 (19.00%). Unmodeled fund value: $66,000.00.`
- The Markdown report gains a **Coverage** section and drops the equal-weight
  caveat sentence, replaced by a statement of what is modeled and what is not.

## Worked Example (for tests)

Portfolio `Example`, total `$100,000`:

| Symbol | Type   | Market Value | Holdings data        |
| ------ | ------ | ------------ | -------------------- |
| NVDA   | equity | $10,000      | n/a (direct)         |
| SCHB   | etf    | $50,000      | weights imported     |
| SCHD   | etf    | $25,000      | seed membership only |
| CASH   | cash   | $15,000      | n/a                  |

SCHB holdings file: `NVDA 7.00`, `AAPL 6.00`, `MSFT 5.00` -> total 18.00%.

Look-through of SCHB (`modeled_share = 0.18`):

```
NVDA  50,000 * 0.07 = 3,500.00
AAPL  50,000 * 0.06 = 3,000.00
MSFT  50,000 * 0.05 = 2,500.00
                      --------
modeled              9,000.00
unmodeled  50,000 - 9,000 = 41,000.00
```

SCHD has no weights -> all $25,000 unmodeled.

Report:

| Symbol | Exposure  | Direct    | Look-through | Exposure % |
| ------ | --------- | --------- | ------------ | ---------- |
| NVDA   | 13,500.00 | 10,000.00 | 3,500.00     | 13.50%     |
| AAPL   |  3,000.00 |      0.00 | 3,000.00     |  3.00%     |
| MSFT   |  2,500.00 |      0.00 | 2,500.00     |  2.50%     |

```
modeled_value        = 10,000 + 9,000 = 19,000.00
unmodeled_fund_value = 41,000 + 25,000 = 66,000.00
cash_value           = 15,000.00
other_value          =      0.00
invariant: 19,000 + 66,000 + 15,000 + 0 = 100,000  OK
```

Compare with today's output, which reports NVDA at $15,000 / 15.00% and shows
nine SCHD names that Atlas has no weight data for at all.

## Edge Cases

- Fund in portfolio with neither weights nor seed membership -> fully unmodeled
  (unchanged behaviour, now explicit in `fund_coverage`).
- Fund whose weights sum to ~100% -> `unmodeled` for that fund is ~0.
- Holdings file containing the fund's own cash sleeve (blank symbol) -> skipped,
  so that share stays unmodeled rather than being attributed to an equity.
- A held name appearing both directly and inside a weighted fund -> summed into
  one line (`direct_value` + `lookthrough_value`), as today.
- Zero or negative portfolio total -> empty report, no division by zero
  (existing test retained).
- Missing portfolio -> `ValueError` (existing behaviour retained).
- Re-running `import-seed` after `import-holdings` -> holdings preserved.
- Re-running `import-holdings` -> full replacement, no accumulation.
- Weight column present but all rows unparseable -> zero holdings stored, and
  the command reports that rather than silently succeeding.

## Testing Plan (TDD)

Each with hand-computed expected values against controlled fixtures, not the
real seed CSV.

- `tests/test_holdings_import.py` (new): header detection across the four
  issuer header styles; preamble/total-row skipping; blank/`--`/`N/A` symbol
  skipping; `%` and quoted weight parsing; duplicate-symbol summing; negative
  weight preserved; fractions guard raises `AtlasDataError`; over-100 guard
  raises; full-file import stores the expected rows with
  `source='holdings_file'`.
- `tests/test_seed_holdings_precedence.py` (new): `import-seed` after
  `import-holdings` leaves `holdings_file` rows and weights intact; a fund
  without imported holdings still gets its seed rows.
- `tests/test_portfolio_analysis.py` (rewrite of four look-through tests):
  weighted look-through math (the worked example above); a no-weights fund
  contributes nothing to `lines` and all of its value to
  `unmodeled_fund_value`; the accounting invariant; `other_value` reported;
  sorting; zero-total; missing portfolio.
- `tests/test_providers.py` (new): each provider satisfies its interface and
  yields the expected records without touching a database.
- `tests/test_reports_and_journal.py` (extend): report contains the Coverage
  section and no equal-weight caveat.

Fixtures: `tests/fixtures/holdings_ishares.csv`, `holdings_schwab.csv`,
`holdings_invesco.csv`, `holdings_vanguard.csv`, `holdings_fractions.csv`
(guard case).

## Files Touched

- `src/atlas/providers/base.py` (add `FundHolding`, `FundHoldingsProvider`)
- `src/atlas/providers/holdings_file.py` (new)
- `src/atlas/providers/seed_universe.py` (new; wraps existing seed parsing)
- `src/atlas/providers/portfolio_files.py` (new; wraps Schwab + portfolio CSV)
- `src/atlas/parsing.py` (new; `parse_money`, `parse_percent`,
  `normalize_asset_type` moved out of `db/database.py` and `scoring/engine.py`)
- `src/atlas/exceptions.py` (add `AtlasDataError`)
- `src/atlas/db/schema.sql` (document `weight` units; no structural change)
- `src/atlas/db/database.py` (`load_fund_holdings`; seed precedence rule;
  helpers moved to `parsing.py`)
- `src/atlas/scoring/engine.py` (drop private `_parse_percent`)
- `tests/test_parsing.py` (import from `atlas.parsing`)
- `src/atlas/portfolio/analysis.py` (weighted engine, coverage, remove
  `portfolio_hidden_concentration`)
- `src/atlas/portfolio/schwab.py` (retrofit onto `PortfolioImportProvider`)
- `src/atlas/cli/main.py` (`import-holdings`, `coverage`, updated
  `analyze-portfolio`)
- `src/atlas/reports/markdown.py` (Coverage section, revised caveats)
- `src/atlas/core/evidence.py` (fix import-time `collected_at` default)
- Tests + fixtures as listed above
- `docs/foundation/ROADMAP_FOUNDATION_PHASE.md`, `docs/ATLAS_v0_7_NOTES.md`
  (new), `pyproject.toml`, `application/kernel.py`, `web/app.py` (0.8.0)

## Implementation Slices

Ordered so each slice leaves the suite green and the tool usable. Slices 1-4
deliver the whole point of this spec; slice 5 is separable and may be dropped
or deferred without weakening the rest.

1. **Parsing foundation** — `atlas/parsing.py`, `AtlasDataError`, schema
   comment. No behaviour change; existing tests must stay green.
2. **Holdings ingestion** — `FundHoldingsProvider`, `HoldingsFileProvider`,
   `load_fund_holdings`, seed precedence rule, `import-holdings` command.
   Atlas can now store real weights; nothing consumes them yet.
3. **Weighted engine** — rewrite `combined_concentration`, add `FundCoverage`
   and the accounting invariant, remove `portfolio_hidden_concentration`. This
   is the slice that changes reported numbers.
4. **Coverage surfacing** — `coverage` command, `analyze-portfolio` coverage
   line, report Coverage section.
5. **Provider retrofits** — `SeedUniverseProvider`, `SchwabPositionsProvider`,
   `PortfolioCsvProvider`. Pure refactor behind unchanged public functions;
   this is what makes the remaining two interfaces live.

Housekeeping (version bump, roadmap renumber, `core/evidence.py` default fix,
v0.7 notes) lands last, once behaviour is settled.

## Version & Roadmap

The repo's convention is that `X.Y.0` means "working toward vX.Y" — it was
already tagged `0.7.0` while v0.7 was unstarted. This work delivers what the
roadmap listed under "Next Model Improvements" (full holdings ingestion,
weighted overlap math), so:

- Roadmap v0.7 becomes **Holdings Ingestion & Weighted Look-Through
  (delivered)**.
- Normalized Schema slides to v0.8, Theme Engine v0.9, Decision Model v1.0,
  First Coherent Local Product v1.1.
- Version bumps to **0.8.0** in `pyproject.toml`, `ATLAS_VERSION`, and
  `web/app.py`. `tests/test_kernel_web_health.py` asserts the version string
  and must be updated with it.

## Rollout / Verification

- Full `uv run pytest` green on 3.11 and 3.13 (CI matrix).
- Manual, against a real downloaded holdings file:
  - `atlas import-holdings SCHB <schb.csv>` reports the stored count and total
    weight.
  - `atlas coverage --name Primary` shows portfolio modeled share rising from
    0% to the imported fund's contribution.
  - `atlas analyze-portfolio --name Primary` shows exact weighted exposure and
    an explicit unmodeled remainder.
  - `atlas serve`, then re-run `atlas coverage` to confirm the seed loader did
    not destroy the imported holdings.
- Confirm `compare-overlap` and `repeat-holdings` still work on funds whose
  rows are now `holdings_file` rather than `seed_top_ten`.
