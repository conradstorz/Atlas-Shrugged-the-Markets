# Schwab Positions Ingestion + Combined Concentration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ingest a real Charles Schwab Positions CSV and report combined hidden concentration (directly-held stocks + ETF/fund look-through).

**Architecture:** A new header-driven parser (`portfolio/schwab.py`) loads positions into the existing `portfolio_position` table using a normalized `asset_type` vocabulary. Shared money/asset-type helpers live in `db/database.py`. A new `combined_concentration()` in `portfolio/analysis.py` sums direct equity exposure with equal-weight ETF/fund look-through and reports coverage. The CLI and Markdown report surface the combined view.

**Tech Stack:** Python 3.11+, stdlib `csv`, SQLite, Typer CLI, pytest. Managed with `uv`.

## Global Constraints

- All commands run via `uv`: `uv run pytest`, `uv run atlas ...`. Never `pip`.
- No new runtime dependencies — stdlib `csv` only.
- Do NOT loosen the `fastapi`/`starlette`/`httpx`/`click` version pins in `pyproject.toml`.
- No database schema migration. Reuse existing `portfolio_position` columns: `symbol, description, asset_type, market_value, notes`.
- Normalized `asset_type` vocabulary is exactly: `equity | etf | mutual_fund | cash | other`.
- Do not chain shell commands with `&&` — run them as separate commands.
- Every git commit message MUST end with this trailer line:
  `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`
- Follow TDD: write the failing test, watch it fail, minimal implementation, watch it pass, commit.

---

### Task 1: Shared money & asset-type parsing helpers

**Files:**
- Modify: `src/atlas/db/database.py` (add two module-level functions near the top, after imports)
- Test: `tests/test_parsing.py` (create)

**Interfaces:**
- Produces:
  - `parse_money(raw: str | None) -> float` — strips `$`/commas, treats `--`/`N/A`/empty/`None` as `0.0`, never raises.
  - `normalize_asset_type(raw: str | None) -> str` — returns one of `equity | etf | mutual_fund | cash | other`.

- [ ] **Step 1: Write the failing test**

Create `tests/test_parsing.py`:

```python
from atlas.db.database import normalize_asset_type, parse_money


def test_parse_money_strips_dollar_and_commas() -> None:
    assert parse_money("$9,846.00") == 9846.0
    assert parse_money("$4.96") == 4.96


def test_parse_money_treats_placeholders_as_zero() -> None:
    assert parse_money("--") == 0.0
    assert parse_money("N/A") == 0.0
    assert parse_money("") == 0.0
    assert parse_money(None) == 0.0


def test_normalize_asset_type_maps_schwab_labels() -> None:
    assert normalize_asset_type("Equity") == "equity"
    assert normalize_asset_type("ETFs & Closed End Funds") == "etf"
    assert normalize_asset_type("Mutual Fund") == "mutual_fund"
    assert normalize_asset_type("Cash and Money Market") == "cash"


def test_normalize_asset_type_handles_legacy_and_unknown() -> None:
    assert normalize_asset_type("ETF") == "etf"
    assert normalize_asset_type("Cash") == "cash"
    assert normalize_asset_type("--") == "other"
    assert normalize_asset_type(None) == "other"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_parsing.py -q`
Expected: FAIL — `ImportError: cannot import name 'normalize_asset_type'`.

- [ ] **Step 3: Write minimal implementation**

In `src/atlas/db/database.py`, after the existing imports and before `connect()`, add:

```python
def parse_money(raw: str | None) -> float:
    """Parse a Schwab-style money cell (``$9,846.00``) into a float.

    Placeholders (``--``, ``N/A``), empty strings, and ``None`` become ``0.0``.
    Never raises on malformed input.
    """
    if raw is None:
        return 0.0
    text = str(raw).strip()
    if text in {"", "--", "N/A"}:
        return 0.0
    text = text.replace("$", "").replace(",", "").strip()
    try:
        return float(text or 0)
    except ValueError:
        return 0.0


def normalize_asset_type(raw: str | None) -> str:
    """Normalize a security-type label to the Atlas vocabulary.

    Returns one of: ``equity``, ``etf``, ``mutual_fund``, ``cash``, ``other``.
    Matching is case-insensitive and substring-based so it tolerates both the
    Schwab labels ("ETFs & Closed End Funds") and legacy CSV values ("ETF").
    """
    text = (raw or "").strip().lower()
    if not text or text in {"--", "n/a"}:
        return "other"
    if "cash" in text or "money market" in text:
        return "cash"
    if "mutual fund" in text:
        return "mutual_fund"
    if "etf" in text or "closed end" in text:
        return "etf"
    if "equity" in text:
        return "equity"
    return "other"
```

- [ ] **Step 4: Run test to verify it passes**

Run: `uv run pytest tests/test_parsing.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/db/database.py tests/test_parsing.py
git commit -m "Add shared money and asset-type parsing helpers

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 2: Normalized asset-type vocabulary in summary + legacy loader

**Files:**
- Modify: `src/atlas/portfolio/analysis.py:7-38` (`PortfolioSummary` dataclass + `summarize_portfolio`)
- Modify: `src/atlas/db/database.py` (`load_portfolio_csv`: use `parse_money` and `normalize_asset_type`)
- Modify: `src/atlas/reports/markdown.py:63-66` (summary lines use new fields)
- Modify: `tests/test_portfolio_analysis.py` (`test_summarize_splits_etf_and_other_value`)

**Interfaces:**
- Consumes: `parse_money`, `normalize_asset_type` (Task 1).
- Produces: `PortfolioSummary(name, position_count, total_value, equity_value, fund_value, cash_value)` where `fund_value` = sum of `etf` + `mutual_fund`.

- [ ] **Step 1: Update the failing test**

In `tests/test_portfolio_analysis.py`, replace `test_summarize_splits_etf_and_other_value` with:

```python
def test_summarize_splits_equity_fund_and_cash_value(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _seed_universe(conn)
    _add_portfolio(
        conn,
        "P",
        [("AAA", 60000, "etf"), ("NVDA", 40000, "equity"), ("CASH", 100000, "cash")],
    )

    summary = summarize_portfolio(conn, "P")

    assert summary.position_count == 3
    assert summary.total_value == 200000
    assert summary.equity_value == 40000
    assert summary.fund_value == 60000
    assert summary.cash_value == 100000
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_portfolio_analysis.py::test_summarize_splits_equity_fund_and_cash_value -q`
Expected: FAIL — `AttributeError: 'PortfolioSummary' object has no attribute 'equity_value'`.

- [ ] **Step 3: Update `PortfolioSummary` and `summarize_portfolio`**

In `src/atlas/portfolio/analysis.py`, replace the dataclass (lines 7-14) and the `summarize_portfolio` body:

```python
@dataclass(frozen=True)
class PortfolioSummary:
    name: str
    position_count: int
    total_value: float
    equity_value: float
    fund_value: float
    cash_value: float


def summarize_portfolio(conn: sqlite3.Connection, portfolio_name: str) -> PortfolioSummary:
    portfolio = conn.execute("SELECT id, name FROM portfolio WHERE name = ?", (portfolio_name,)).fetchone()
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_name}")
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS position_count,
            COALESCE(SUM(market_value), 0) AS total_value,
            COALESCE(SUM(CASE WHEN asset_type = 'equity' THEN market_value ELSE 0 END), 0) AS equity_value,
            COALESCE(SUM(CASE WHEN asset_type IN ('etf', 'mutual_fund') THEN market_value ELSE 0 END), 0) AS fund_value,
            COALESCE(SUM(CASE WHEN asset_type = 'cash' THEN market_value ELSE 0 END), 0) AS cash_value
        FROM portfolio_position
        WHERE portfolio_id = ?
        """,
        (portfolio["id"],),
    ).fetchone()
    return PortfolioSummary(
        name=portfolio["name"],
        position_count=int(row["position_count"]),
        total_value=float(row["total_value"]),
        equity_value=float(row["equity_value"]),
        fund_value=float(row["fund_value"]),
        cash_value=float(row["cash_value"]),
    )
```

- [ ] **Step 4: Update `load_portfolio_csv` to normalize**

In `src/atlas/db/database.py`, inside `load_portfolio_csv`, change the market-value parse and the asset-type insert value:

Replace:
```python
            raw_value = row.get("Market Value") or row.get("Value") or row.get("Amount") or "0"
            market_value = float(str(raw_value).replace("$", "").replace(",", "").strip() or 0)
```
with:
```python
            raw_value = row.get("Market Value") or row.get("Value") or row.get("Amount") or "0"
            market_value = parse_money(raw_value)
```

Replace the `row.get("Asset Type", "ETF"),` insert argument with:
```python
                    normalize_asset_type(row.get("Asset Type", "ETF")),
```

- [ ] **Step 5: Update the Markdown report summary lines**

In `src/atlas/reports/markdown.py`, replace the two summary value lines (currently `ETF value` / `Cash or unknown value`) with:

```python
            f"- Equity value: {_money(summary.equity_value)}",
            f"- Fund value (ETF + mutual): {_money(summary.fund_value)}",
            f"- Cash value: {_money(summary.cash_value)}",
```

- [ ] **Step 6: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (all tests green; `test_report_can_include_private_portfolio` still passes because the `## Portfolio:` and `Estimated Hidden Concentration` headings are unchanged in this task).

- [ ] **Step 7: Commit**

```bash
git add src/atlas/portfolio/analysis.py src/atlas/db/database.py src/atlas/reports/markdown.py tests/test_portfolio_analysis.py
git commit -m "Adopt normalized equity/fund/cash vocabulary in portfolio summary

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 3: Schwab positions parser

**Files:**
- Create: `src/atlas/portfolio/schwab.py`
- Create: `tests/fixtures/schwab_positions_sample.csv`
- Test: `tests/test_schwab_import.py` (create)

**Interfaces:**
- Consumes: `connect` (existing), `parse_money`, `normalize_asset_type` (Task 1).
- Produces: `load_schwab_positions(conn: sqlite3.Connection, portfolio_name: str, path: Path) -> int` — inserts positions, returns the count inserted. The cash row is stored under synthetic symbol `CASH`.

- [ ] **Step 1: Create the test fixture**

Create `tests/fixtures/schwab_positions_sample.csv` with exactly this content:

```
"Positions for account CFS-Play Money ...572 as of 09:27 PM ET, 2026/07/08"

"Symbol","Description","% of Acct (% of Account)","Mkt Val (Market Value)","Div Yld (Dividend Yield)","Cost/Share","Close","Last","Asset Type",
"NVDA","NVIDIA CORP","5.7%","$10,410.12","0.51%","$129.04","196.93","203.62","Equity",
"GILD","GILEAD SCIENCES INC","9.3%","$16,977.50","2.53%","$111.76","136.36","135.00","Equity",
"SCHD","SCHWAB U.S. DIVIDEND EQUITY ETF","1.61%","$2,942.94","3.13%","$31.42","32.54","32.37","ETFs & Closed End Funds",
"FSELX","FIDELITY SELECT SEMICONDUCTORS","4.48%","$8,184.69","N/A","$38.21","63.20","65.01","Mutual Fund",
"Cash & Cash Investments","--","0.02%","$27.81","--","--","--","--","Cash and Money Market",
"Positions Total","","--","$38,543.06","--","--","--","--","--",
```

- [ ] **Step 2: Write the failing test**

Create `tests/test_schwab_import.py`:

```python
from pathlib import Path

from atlas.db.database import connect
from atlas.portfolio.schwab import load_schwab_positions

FIXTURE = Path("tests/fixtures/schwab_positions_sample.csv")


def test_import_counts_positions_and_skips_preamble_and_total(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    count = load_schwab_positions(conn, "Primary", FIXTURE)
    # NVDA, GILD, SCHD, FSELX, CASH -> 5. Preamble and "Positions Total" skipped.
    assert count == 5


def test_import_normalizes_asset_types_and_values(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_schwab_positions(conn, "Primary", FIXTURE)
    rows = {
        r["symbol"]: r
        for r in conn.execute(
            "SELECT symbol, asset_type, market_value FROM portfolio_position"
        ).fetchall()
    }

    assert rows["NVDA"]["asset_type"] == "equity"
    assert rows["NVDA"]["market_value"] == 10410.12
    assert rows["SCHD"]["asset_type"] == "etf"
    assert rows["FSELX"]["asset_type"] == "mutual_fund"
    assert rows["CASH"]["asset_type"] == "cash"
    assert rows["CASH"]["market_value"] == 27.81


def test_reimport_replaces_existing_positions(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_schwab_positions(conn, "Primary", FIXTURE)
    load_schwab_positions(conn, "Primary", FIXTURE)
    count = conn.execute("SELECT COUNT(*) AS c FROM portfolio_position").fetchone()["c"]
    assert count == 5
```

- [ ] **Step 3: Run test to verify it fails**

Run: `uv run pytest tests/test_schwab_import.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'atlas.portfolio.schwab'`.

- [ ] **Step 4: Implement the parser**

Create `src/atlas/portfolio/schwab.py`:

```python
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

from atlas.db.database import normalize_asset_type, parse_money

CASH_ROW_LABEL = "Cash & Cash Investments"
_SKIP_SYMBOLS = {"Positions Total"}


def _column(header: dict[str, int], *candidates: str) -> int | None:
    """Return the index of the first header cell containing any candidate text."""
    for candidate in candidates:
        for name, idx in header.items():
            if candidate.lower() in name.lower():
                return idx
    return None


def load_schwab_positions(conn: sqlite3.Connection, portfolio_name: str, path: Path) -> int:
    """Load a Schwab "Positions" CSV export into ``portfolio_position``.

    Skips the preamble, blank lines, and the "Positions Total" row. Columns are
    located by name from the header row (the row whose first cell is "Symbol"),
    so column reordering is tolerated. The "Cash & Cash Investments" row is
    stored under the synthetic symbol ``CASH``. Existing positions for the
    portfolio are replaced.
    """
    conn.execute(
        "INSERT INTO portfolio (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
        (portfolio_name,),
    )
    portfolio_id = conn.execute(
        "SELECT id FROM portfolio WHERE name = ?", (portfolio_name,)
    ).fetchone()["id"]
    conn.execute("DELETE FROM portfolio_position WHERE portfolio_id = ?", (portfolio_id,))

    count = 0
    header: dict[str, int] | None = None
    with path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        for cells in csv.reader(csv_file):
            if not cells or not cells[0].strip():
                continue
            first = cells[0].strip()

            if first == "Symbol":
                header = {name.strip(): idx for idx, name in enumerate(cells)}
                continue
            if header is None:
                continue  # preamble before the first header
            if first in _SKIP_SYMBOLS or first.startswith("Positions for account"):
                continue

            symbol = "CASH" if first == CASH_ROW_LABEL else first.upper()

            desc_idx = _column(header, "Description")
            value_idx = _column(header, "Market Value", "Mkt Val")
            asset_idx = _column(header, "Asset Type")

            description = cells[desc_idx].strip() if desc_idx is not None else ""
            market_value = parse_money(cells[value_idx] if value_idx is not None else None)
            asset_type = normalize_asset_type(cells[asset_idx] if asset_idx is not None else None)

            conn.execute(
                """
                INSERT INTO portfolio_position (
                    portfolio_id, symbol, description, asset_type, market_value
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(portfolio_id, symbol) DO UPDATE SET
                    description=excluded.description,
                    asset_type=excluded.asset_type,
                    market_value=excluded.market_value
                """,
                (portfolio_id, symbol, description, asset_type, market_value),
            )
            count += 1
    conn.commit()
    return count
```

- [ ] **Step 5: Run test to verify it passes**

Run: `uv run pytest tests/test_schwab_import.py -q`
Expected: PASS (3 passed).

- [ ] **Step 6: Commit**

```bash
git add src/atlas/portfolio/schwab.py tests/test_schwab_import.py tests/fixtures/schwab_positions_sample.csv
git commit -m "Add Schwab positions CSV parser

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 4: Combined concentration engine

**Files:**
- Modify: `src/atlas/portfolio/analysis.py` (add dataclasses + `combined_concentration`)
- Modify: `tests/test_portfolio_analysis.py` (add combined-concentration tests)

**Interfaces:**
- Consumes: `portfolio_position` rows with normalized `asset_type`; `etf_holding` rows.
- Produces:
  - `ConcentrationLine(symbol, exposure_value, exposure_percent, direct_value, lookthrough_value, source_funds)` (frozen dataclass; `source_funds: list[str]`).
  - `ConcentrationReport(lines, total_value, unmodeled_fund_value)` (frozen dataclass; `lines: list[ConcentrationLine]` sorted by `exposure_percent` desc then `symbol`).
  - `combined_concentration(conn, portfolio_name: str, limit: int = 25) -> ConcentrationReport`.

- [ ] **Step 1: Write the failing tests**

Add to `tests/test_portfolio_analysis.py` (imports at top: add `combined_concentration`, `ConcentrationReport` from `atlas.portfolio.analysis`):

```python
def test_combined_concentration_sums_direct_and_lookthrough(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # FUND holds {NVDA, AAPL}; portfolio holds NVDA directly and FUND.
    conn.execute("INSERT INTO etf (symbol, description) VALUES ('FUND', 'A fund')")
    for rank, h in enumerate(["NVDA", "AAPL"], start=1):
        conn.execute(
            "INSERT INTO etf_holding (etf_symbol, holding_symbol, rank) VALUES ('FUND', ?, ?)",
            (h, rank),
        )
    conn.commit()
    _add_portfolio(conn, "P", [("NVDA", 100, "equity"), ("FUND", 100, "etf")])

    report = combined_concentration(conn, "P")
    by_symbol = {line.symbol: line for line in report.lines}

    assert report.total_value == 200
    # NVDA: 100 direct + 100/2 look-through = 150 -> 75%
    assert by_symbol["NVDA"].exposure_value == 150.0
    assert by_symbol["NVDA"].exposure_percent == 75.0
    assert by_symbol["NVDA"].direct_value == 100.0
    assert by_symbol["NVDA"].lookthrough_value == 50.0
    assert by_symbol["NVDA"].source_funds == ["FUND"]
    # AAPL: 50 look-through only -> 25%
    assert by_symbol["AAPL"].exposure_value == 50.0
    assert by_symbol["AAPL"].direct_value == 0.0
    assert report.unmodeled_fund_value == 0.0


def test_combined_concentration_reports_unmodeled_fund_value(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # FUND has no parsed holdings -> cannot be looked through.
    _add_portfolio(conn, "P", [("NVDA", 100, "equity"), ("FUND", 100, "etf")])

    report = combined_concentration(conn, "P")
    by_symbol = {line.symbol: line for line in report.lines}

    assert by_symbol["NVDA"].exposure_value == 100.0
    assert by_symbol["NVDA"].exposure_percent == 50.0
    assert "FUND" not in by_symbol
    assert report.unmodeled_fund_value == 100.0


def test_combined_concentration_sorted_desc(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_portfolio(conn, "P", [("NVDA", 100, "equity"), ("AAPL", 300, "equity")])

    report = combined_concentration(conn, "P")

    assert [line.symbol for line in report.lines] == ["AAPL", "NVDA"]


def test_combined_concentration_zero_total_is_empty(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    _add_portfolio(conn, "P", [("NVDA", 0, "equity")])

    report = combined_concentration(conn, "P")

    assert report.lines == []
    assert report.total_value == 0.0


def test_combined_concentration_missing_portfolio_raises(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    with pytest.raises(ValueError):
        combined_concentration(conn, "nope")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest tests/test_portfolio_analysis.py -k combined -q`
Expected: FAIL — `ImportError: cannot import name 'combined_concentration'`.

- [ ] **Step 3: Implement the engine**

In `src/atlas/portfolio/analysis.py`, add these dataclasses (below the existing `PortfolioSummary`) and function:

```python
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
    lines: list[ConcentrationLine]
    total_value: float
    unmodeled_fund_value: float


def combined_concentration(
    conn: sqlite3.Connection, portfolio_name: str, limit: int = 25
) -> ConcentrationReport:
    """Estimate per-name exposure combining direct holdings and fund look-through.

    Direct ``equity`` positions contribute their full market value. ``etf`` and
    ``mutual_fund`` positions with parsed top-ten holdings distribute their value
    equally across those holdings (equal-weight prototype). Fund value with no
    parsed holdings is reported as ``unmodeled_fund_value``.
    """
    portfolio = conn.execute(
        "SELECT id FROM portfolio WHERE name = ?", (portfolio_name,)
    ).fetchone()
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_name}")
    portfolio_id = portfolio["id"]

    total_value = float(
        conn.execute(
            "SELECT COALESCE(SUM(market_value), 0) AS total FROM portfolio_position WHERE portfolio_id = ?",
            (portfolio_id,),
        ).fetchone()["total"]
    )
    if total_value <= 0:
        return ConcentrationReport(lines=[], total_value=0.0, unmodeled_fund_value=0.0)

    direct: dict[str, float] = {}
    lookthrough: dict[str, float] = {}
    sources: dict[str, set[str]] = {}

    for row in conn.execute(
        "SELECT symbol, market_value FROM portfolio_position "
        "WHERE portfolio_id = ? AND asset_type = 'equity'",
        (portfolio_id,),
    ):
        direct[row["symbol"]] = direct.get(row["symbol"], 0.0) + float(row["market_value"])

    unmodeled_fund_value = 0.0
    funds = conn.execute(
        "SELECT symbol, market_value FROM portfolio_position "
        "WHERE portfolio_id = ? AND asset_type IN ('etf', 'mutual_fund')",
        (portfolio_id,),
    ).fetchall()
    for fund in funds:
        holdings = conn.execute(
            "SELECT holding_symbol FROM etf_holding WHERE etf_symbol = ?",
            (fund["symbol"],),
        ).fetchall()
        if not holdings:
            unmodeled_fund_value += float(fund["market_value"])
            continue
        share = float(fund["market_value"]) / len(holdings)
        for holding in holdings:
            symbol = holding["holding_symbol"]
            lookthrough[symbol] = lookthrough.get(symbol, 0.0) + share
            sources.setdefault(symbol, set()).add(fund["symbol"])

    lines: list[ConcentrationLine] = []
    for symbol in set(direct) | set(lookthrough):
        direct_value = direct.get(symbol, 0.0)
        lookthrough_value = lookthrough.get(symbol, 0.0)
        exposure = direct_value + lookthrough_value
        lines.append(
            ConcentrationLine(
                symbol=symbol,
                exposure_value=round(exposure, 2),
                exposure_percent=round(exposure / total_value * 100, 2),
                direct_value=round(direct_value, 2),
                lookthrough_value=round(lookthrough_value, 2),
                source_funds=sorted(sources.get(symbol, set())),
            )
        )
    lines.sort(key=lambda line: (-line.exposure_percent, line.symbol))
    return ConcentrationReport(
        lines=lines[:limit],
        total_value=round(total_value, 2),
        unmodeled_fund_value=round(unmodeled_fund_value, 2),
    )
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest tests/test_portfolio_analysis.py -q`
Expected: PASS (all tests in file green).

- [ ] **Step 5: Commit**

```bash
git add src/atlas/portfolio/analysis.py tests/test_portfolio_analysis.py
git commit -m "Add combined direct + look-through concentration engine

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

### Task 5: Surface via CLI and Markdown report

**Files:**
- Modify: `src/atlas/cli/main.py` (add `import-schwab`; switch `analyze-portfolio` to combined view)
- Modify: `src/atlas/reports/markdown.py` (combined concentration table + coverage)
- Modify: `tests/test_reports_and_journal.py` (`test_report_can_include_private_portfolio` heading)
- Test: `tests/test_web_app.py` unaffected; run full suite.

**Interfaces:**
- Consumes: `load_schwab_positions` (Task 3), `combined_concentration`, `ConcentrationReport`, `summarize_portfolio` (Tasks 2, 4).

- [ ] **Step 1: Update the report test (failing)**

In `tests/test_reports_and_journal.py`, change the assertion in `test_report_can_include_private_portfolio`:

```python
    assert "## Portfolio: Primary" in report
    assert "Combined Concentration" in report
    assert "not looked through" in report
```

- [ ] **Step 2: Run test to verify it fails**

Run: `uv run pytest tests/test_reports_and_journal.py::test_report_can_include_private_portfolio -q`
Expected: FAIL — `assert 'Combined Concentration' in report` (report still uses the old heading).

- [ ] **Step 3: Update the Markdown report**

In `src/atlas/reports/markdown.py`, replace the import of `portfolio_hidden_concentration` with `combined_concentration`:

```python
from atlas.portfolio.analysis import combined_concentration, summarize_portfolio
```

Replace the portfolio concentration section (the `### Estimated Hidden Concentration` block and its `for row in portfolio_hidden_concentration(...)` loop) with:

```python
        report_data = combined_concentration(conn, portfolio_name, limit=25)
        lines.extend([
            "",
            "### Combined Concentration",
            "",
            "Per-name exposure combining directly-held positions with equal-weight "
            "ETF/fund look-through. Direct dollars are exact; look-through is a "
            "prototype estimate from parsed top-ten holdings.",
            "",
            "| Symbol | Exposure % | Exposure | Direct | Look-through | Source Funds |",
            "|---|---:|---:|---:|---:|---|",
        ])
        for line in report_data.lines:
            lines.append(
                f"| {line.symbol} | {line.exposure_percent:.2f}% | {_money(line.exposure_value)} | "
                f"{_money(line.direct_value)} | {_money(line.lookthrough_value)} | "
                f"{', '.join(line.source_funds) or '-'} |"
            )
        lines.extend([
            "",
            f"Fund value not looked through: {_money(report_data.unmodeled_fund_value)}.",
        ])
```

- [ ] **Step 4: Add the `import-schwab` command and update `analyze-portfolio`**

In `src/atlas/cli/main.py`, update the analysis import line to:

```python
from atlas.portfolio.analysis import combined_concentration, summarize_portfolio
from atlas.portfolio.schwab import load_schwab_positions
```

Add a new command (place it after `import_portfolio`):

```python
@app.command("import-schwab")
def import_schwab(
    positions_csv: Path = typer.Argument(..., help="Schwab Positions CSV export."),
    name: str = typer.Option("Primary", help="Portfolio name."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
) -> None:
    """Import a Charles Schwab Positions CSV export."""
    conn = connect(db)
    count = load_schwab_positions(conn, name, positions_csv)
    summary = summarize_portfolio(conn, name)
    console.print(f"Imported {count} Schwab positions into portfolio '{summary.name}'.")
    console.print(
        f"Total: ${summary.total_value:,.2f} — equity ${summary.equity_value:,.2f}, "
        f"funds ${summary.fund_value:,.2f}, cash ${summary.cash_value:,.2f}"
    )
```

Replace the body of `analyze_portfolio` after the summary prints (the `rows = portfolio_hidden_concentration(...)` block through the final `console.print`) with:

```python
    report = combined_concentration(conn, name, limit=limit)
    table = Table(title="Combined Concentration (Direct + ETF/Fund Look-Through)")
    table.add_column("Symbol")
    table.add_column("Exposure %", justify="right")
    table.add_column("Exposure", justify="right")
    table.add_column("Direct", justify="right")
    table.add_column("Look-through", justify="right")
    table.add_column("Source Funds")
    for line in report.lines:
        table.add_row(
            line.symbol,
            f"{line.exposure_percent:.2f}%",
            f"${line.exposure_value:,.2f}",
            f"${line.direct_value:,.2f}",
            f"${line.lookthrough_value:,.2f}",
            ", ".join(line.source_funds) or "-",
        )
    console.print(table)
    console.print(f"\nFund value not looked through: ${report.unmodeled_fund_value:,.2f}")
    console.print(
        "Note: look-through uses the equal-weight top-ten prototype; direct holdings are exact."
    )
```

Also update the summary prints in `analyze_portfolio` to include the breakdown (replace the existing `console.print(f"Total value: ...")` line):

```python
    console.print(
        f"Total value: ${summary.total_value:,.2f} — equity ${summary.equity_value:,.2f}, "
        f"funds ${summary.fund_value:,.2f}, cash ${summary.cash_value:,.2f}"
    )
```

Remove the now-unused `portfolio_hidden_concentration` import from `cli/main.py` (keep `combined_concentration`, `summarize_portfolio`).

- [ ] **Step 5: Run the full suite**

Run: `uv run pytest -q`
Expected: PASS (all green).

- [ ] **Step 6: Manual verification against the real sample**

Run each as a separate command:

```bash
uv run atlas import-schwab "tests/fixtures/schwab_positions_sample.csv" --name Play --db ./scratch_schwab.db
```
Expected: `Imported 5 Schwab positions into portfolio 'Play'.` and a total of `$38,543.06`.

```bash
uv run atlas analyze-portfolio --name Play --db ./scratch_schwab.db
```
Expected: a Combined Concentration table led by the direct equities (GILD, NVDA); "Fund value not looked through" reflects SCHD + FSELX ($11,127.63) if those funds are absent from the seed in this DB.

```bash
rm -f ./scratch_schwab.db
```

- [ ] **Step 7: Commit**

```bash
git add src/atlas/cli/main.py src/atlas/reports/markdown.py tests/test_reports_and_journal.py
git commit -m "Surface Schwab import and combined concentration in CLI and report

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>"
```

---

## Self-Review Notes

- **Spec coverage:** parser (Task 3), normalized vocabulary + summary (Task 2), shared helpers (Task 1), combined concentration with coverage (Task 4), CLI + report surfacing (Task 5), worked example (Task 4 tests), edge cases zero-total/missing-portfolio/placeholders/total-row (Tasks 1, 3, 4). All spec sections mapped.
- **Retained:** `portfolio_hidden_concentration` stays in `analysis.py` for its existing tests; no longer on the CLI/report path (per spec).
- **No schema migration:** all new data uses existing `portfolio_position` columns.
