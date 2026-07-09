# Schwab Positions Ingestion + Combined Concentration — Design

Date: 2026-07-08
Status: Approved (pending spec review)

## Overview

Atlas can currently import a simple `Symbol, Market Value` portfolio CSV and
estimate hidden concentration only through ETF top-ten holdings. This work adds:

1. Ingestion of a real Charles Schwab **Positions** CSV export (individual
   stocks, ETFs, mutual funds, and cash).
2. An upgraded concentration engine that combines **directly-held equities**
   with **ETF/fund look-through**, giving the true per-name exposure.

No schema migration is required. All work is local-first; no external calls.

## Goals

- Parse the Schwab Positions export robustly into `portfolio_position`.
- Normalize position types to `equity | etf | mutual_fund | cash`.
- Report combined concentration: for each underlying symbol, exposure held
  directly **plus** exposure hidden inside ETFs/funds.
- Be honest about coverage: report how much fund value could not be
  looked through (funds not in the seed universe).

## Non-Goals (YAGNI)

- Capturing cost basis, quantity, dividend yield, or gain/loss (the export has
  no quantity column; no current feature needs these).
- Real (weighted) fund holdings. Look-through keeps the existing equal-weight
  top-ten prototype until real holdings data is added.
- Transaction history, multi-currency, or options-specific handling.
- Auto-detecting file format. Schwab ingestion is an explicit command.

## Input Format

Example (obscured) export structure:

```
"Positions for account CFS-Play Money ...572 as of 09:27 PM ET, 2026/07/08"

"Symbol","Description","% of Acct (% of Account)","Mkt Val (Market Value)","Div Yld (Dividend Yield)","Cost/Share","Close","Last","Asset Type",
"NVDA","NVIDIA CORP","5.7%","$10,410.12","0.51%","$129.04","196.93","203.62","Equity",
"SCHD","SCHWAB U.S. DIVIDEND EQUITY ETF","1.61%","$2,942.94","3.13%","$31.42","32.54","32.37","ETFs & Closed End Funds",
"FSELX","FIDELITY SELECT SEMICONDUCTORS","4.48%","$8,184.69","N/A","$38.21","63.20","65.01","Mutual Fund",
"Cash & Cash Investments","--","0.02%","$27.81","--","--","--","--","Cash and Money Market",
"Positions Total","","--","$182,504.11","--","--","--","--","--",
```

Characteristics the parser must handle:

- A preamble line (row 1) and a blank line before the header.
- Header row identified by its first cell being `Symbol`.
- Money formatted as `"$9,846.00"`; placeholders `--` and `N/A`; empty cells.
- A `Cash & Cash Investments` row (Symbol is that literal string).
- A trailing `Positions Total` row that must be skipped.
- A trailing empty 10th column (trailing comma in every row).
- Possibly multiple account sections in one file (each with its own preamble
  and header); the parser handles this by processing every recognizable data
  row and skipping preamble/blank/total rows wherever they appear.

## Component Design

### 1. Parser — `src/atlas/portfolio/schwab.py` (new)

```
load_schwab_positions(conn, portfolio_name: str, path: Path) -> int
```

- Reads the CSV with `csv.reader` (not `DictReader`, because of the preamble).
- Locates header rows by matching a row whose first cell is `Symbol`; builds a
  column-name -> index map from that header so column reordering is tolerated.
- For each subsequent row until the next header/preamble/blank:
  - Skip if Symbol is empty, `Positions Total`, or a preamble string.
  - Extract Symbol, Description, Market Value, Asset Type by mapped index.
  - Parse market value via a shared money parser (`$`, `,`, `--`, `N/A`, ``
    -> `0.0`).
  - Normalize Asset Type (see vocabulary below).
  - The cash row (`Cash & Cash Investments`) is stored with synthetic symbol
    `CASH` and type `cash`.
- Replaces existing positions for the portfolio (same pattern as
  `load_portfolio_csv`): upsert portfolio, delete its positions, insert fresh.
- Returns the number of positions inserted.

Shared helpers extracted to avoid duplication with `load_portfolio_csv`:
- `_parse_money(raw: str | None) -> float`
- `_normalize_asset_type(raw: str) -> str`

### 2. Asset-type vocabulary + summary

Normalized `asset_type` values stored in `portfolio_position`:

| Schwab "Asset Type"        | normalized    |
|----------------------------|---------------|
| Equity                     | `equity`      |
| ETFs & Closed End Funds    | `etf`         |
| Mutual Fund                | `mutual_fund` |
| Cash and Money Market      | `cash`        |
| (anything else / `--`)     | `other`       |

`summarize_portfolio` changes its `PortfolioSummary` from the current
`etf_value / cash_or_unknown_value` split to:

```
PortfolioSummary(
    name, position_count, total_value,
    equity_value,   # sum of asset_type='equity'
    fund_value,     # sum of asset_type in ('etf','mutual_fund')
    cash_value,     # sum of asset_type='cash'
)
```

`load_portfolio_csv` (the simple existing loader) is updated to normalize its
`Asset Type` column into the same vocabulary so both loaders agree. The
`examples/sample_portfolio.csv` and existing tests that assert on `etf_value`
/ `cash_or_unknown_value` / `asset_type='ETF'` are updated to the new
vocabulary.

### 3. Combined concentration — `portfolio/analysis.py`

New function:

```
combined_concentration(conn, portfolio_name: str, limit: int = 25)
    -> ConcentrationReport
```

Algorithm (pure Python over two queries):

1. `total_value` = sum of all positions in the portfolio. If `0`, return an
   empty report (no division).
2. **Direct exposure**: for each `equity` position, add its full market value
   to `exposure[symbol]`, tagged source = "direct".
3. **Look-through exposure**: for each `etf`/`mutual_fund` position that has
   parsed rows in `etf_holding`, distribute its market value equally across its
   top-ten holdings: each holding gets `market_value / holding_count`. Add to
   `exposure[holding_symbol]`, tagged with the source fund.
4. Per underlying symbol, record: total exposure `$`, `% of portfolio`, the
   direct vs look-through dollar split, and the set of source funds.
5. **Coverage**: sum the market value of `etf`/`mutual_fund` positions that had
   **no** parsed holdings (`unmodeled_fund_value`) so the report states how much
   of the portfolio's fund exposure is not yet looked through.

Return type:

```
@dataclass(frozen=True)
class ConcentrationLine:
    symbol: str
    exposure_value: float
    exposure_percent: float
    direct_value: float
    lookthrough_value: float
    source_funds: list[str]

@dataclass(frozen=True)
class ConcentrationReport:
    lines: list[ConcentrationLine]        # sorted by exposure_percent desc
    total_value: float
    unmodeled_fund_value: float
```

No double-counting: a symbol is either a fund (looked through) or a direct
equity; fund tickers are not themselves equity positions.

`combined_concentration` runs its own two queries (it does not call the old
function). The existing `portfolio_hidden_concentration` (ETF-only pass-through)
is retained for backward compatibility and its current tests, but is no longer
on the CLI/report path.

### 4. CLI + report surfacing

- New command `atlas import-schwab <csv> [--name Primary] [--db ...]` calling
  `load_schwab_positions`, then printing the summary.
- `atlas analyze-portfolio` switches to `combined_concentration`: a table of
  top exposures with columns `Symbol | Exposure % | Exposure $ | Direct $ |
  Look-through $ | Source Funds`, plus a footer line for
  `unmodeled_fund_value`.
- `reports/markdown.py` renders the same combined view (and coverage note) in
  the portfolio section.

## Worked Example (for tests)

Universe: ETF `FUND` holds top-ten `[NVDA, AAPL]` (2 holdings).
Portfolio: `NVDA` equity `$100`, `FUND` etf `$100`, `CASH` cash `$0`.
Total = `$200`.

- NVDA: direct `$100` + look-through `$100/2 = $50` = `$150` -> `75%`,
  direct `$100`, look-through `$50`, source funds `[FUND]`.
- AAPL: look-through `$50` -> `25%`, direct `$0`, source funds `[FUND]`.
- `unmodeled_fund_value = $0` (FUND had holdings).

If instead `FUND` has no parsed holdings: NVDA = `$100` (`50%`, direct only),
`unmodeled_fund_value = $100`.

## Edge Cases

- Empty / zero total value -> empty report, no divide-by-zero.
- Money cells `--`, `N/A`, empty -> `0.0`.
- `Positions Total` and preamble rows -> skipped.
- Warrants / dead tickers (`$0.00`, tiny values) -> stored as `equity`
  positions with their value (no special filtering; data is not editorialized).
- Same symbol across multiple account sections of one file -> market value is
  summed (accumulated on `UNIQUE(portfolio_id, symbol)` conflict), so an
  "All Accounts" export gives combined household exposure. Within a single
  account Schwab lists each symbol once. The returned count is the number of
  distinct stored positions.
- Fund present in portfolio but absent from `etf_holding` -> contributes to
  `unmodeled_fund_value`, not to look-through exposure.

## Testing Plan (TDD)

New/updated tests, each with hand-computed expected values against controlled
fixtures (not the real seed CSV):

- `test_schwab_import.py`: header detection, preamble/total skipping, money
  parsing, asset-type normalization, cash-row handling, position count, and
  parsing the provided obscured sample end-to-end.
- `test_portfolio_analysis.py` (extend): `combined_concentration` direct-only,
  look-through-only, combined, coverage/unmodeled value, zero-total, sorting,
  and no-double-count. Update `summarize_portfolio` tests to the new vocabulary.
- Update existing tests/`examples/sample_portfolio.csv` for the normalized
  asset types.

## Files Touched

- `src/atlas/portfolio/schwab.py` (new)
- `src/atlas/portfolio/analysis.py` (summary + combined concentration)
- `src/atlas/db/database.py` (normalize asset type in `load_portfolio_csv`;
  shared money parser)
- `src/atlas/cli/main.py` (`import-schwab`; updated `analyze-portfolio`)
- `src/atlas/reports/markdown.py` (combined view + coverage)
- `tests/test_schwab_import.py` (new), `tests/test_portfolio_analysis.py`
  (extend), other affected tests + `examples/sample_portfolio.csv`

## Rollout / Verification

- Full `uv run pytest` green.
- Manual: `uv run atlas import-schwab <sample>` then `analyze-portfolio` and
  `generate-report` against the obscured sample, confirming the direct-stock
  concentration (NVDA, GILD, SYY, KR, MO, ...) appears and coverage reflects the
  seed-absent funds.
```
