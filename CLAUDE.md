# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Atlas is a private, local-first decision intelligence platform for long-term investors ("Maps, not predictions"). It scores ETFs, detects hidden concentration across ETF holdings, analyzes private portfolios, and keeps a decision journal — all against a local SQLite database, with no external market-data calls yet.

## Commands

Uses `uv` for all dependency management and execution (Python >= 3.11).

```bash
uv sync                              # install dependencies
uv run pytest                        # run all tests
uv run pytest tests/test_scoring.py::test_name   # run a single test
uv run atlas --help                  # list all CLI commands
```

Key application commands (all accept `--db` and most accept `--seed`):

```bash
uv run atlas kernel-check                          # start/stop the Kernel, print health
uv run atlas serve                                 # FastAPI dashboard at http://127.0.0.1:8000
uv run atlas import-seed --seed data/atlas_seed_universe.csv
uv run atlas score-etfs                            # heuristic ETF scores
uv run atlas compare-overlap SPY QQQ               # top-ten holdings overlap
uv run atlas import-portfolio examples/sample_portfolio.csv
uv run atlas analyze-portfolio                     # estimate hidden concentration
uv run atlas generate-report                       # portable Markdown research report
uv run atlas journal-add SYM --decision buy --thesis "..."
```

The local database defaults to `.atlas/atlas.db` (gitignored). Health endpoints when serving: `/health`, `/ready`, `/version`.

## Architecture

The codebase is deliberately split into two layers with a hard boundary between them (see `specifications/adr/ADR-0002`). Understanding this split is the key to working here.

### Kernel / platform layer (investment-agnostic)

`platform/`, `application/`, `plugins/`, `exceptions.py` form the **Atlas Kernel** — the platform spine. It owns only config, secrets, logging, plugin lifecycle, health reporting, and app lifecycle. **It must never import or contain investment concepts** (ETFs, portfolios, scores, market data). This constraint is intentional and enforced by convention, not tooling — preserve it when editing.

- `application/kernel.py` — `AtlasKernel` orchestrates the startup/shutdown sequence: validate config → make data dir → configure logging → initialize plugins. `from_environment()` is the standard constructor.
- `platform/config.py` — immutable `AtlasConfig`, loaded from `ATLAS_*` env vars, self-validating.
- `platform/secrets.py` — `SecretProvider` protocol; `SecretValue` redacts on `str`/`repr` and only reveals via `.reveal()`.
- `platform/plugins.py` — `AtlasPlugin` protocol + `PluginHost`. New capabilities are meant to attach as plugins (see `plugins/hello.py`) without modifying Kernel code.

### Investment / domain layer

The actual investment features live outside the Kernel and are wired together by the CLI and web app, not by the Kernel:

- `db/database.py` + `db/schema.sql` — SQLite is the single source of truth. `connect()` applies the schema on every open (idempotent `CREATE TABLE IF NOT EXISTS`). Loaders parse the seed CSV's pipe-delimited top-ten holdings format (`|NVDA||AAPL|`) into the `etf_holding` table.
- `scoring/engine.py` — the **concrete, active** ETF scorer: a transparent text/keyword + expense-ratio heuristic producing a 0–100 score with an explanation string. This is what the CLI and web app call. Explicitly a prototype ("v0.2/v0.4 heuristic"), meant to be refined with real holdings/valuation data.
- `analytics/overlap.py`, `portfolio/analysis.py`, `journal/service.py`, `reports/markdown.py` — feature modules, each a thin set of functions operating on a `sqlite3.Connection`.
- `cli/main.py` — Typer app; the primary entry point (`atlas = "atlas.cli.main:app"`). Each command opens a DB connection and calls into the feature modules.
- `web/app.py` — FastAPI dashboard. Renders server-side HTML by string templating. Note it re-runs `AtlasKernel` per health request and re-scores ETFs on each page load (no caching).

### `core/` — aspirational abstractions (mostly not yet wired in)

`core/` (scoring, decisions, evidence, themes), `models/domain.py`, and `providers/base.py` define stable, framework-free abstractions (`ExplainableScore`, `InvestmentThesis`, `ResearchDataProvider`, etc.) intended to be the durable domain model as Atlas grows. **These are largely not yet used by the running code** — the live path uses `scoring/engine.py` and raw SQLite rows, not these types. Don't assume `core/` is the active implementation; check the CLI/web call graph.

## Governance & docs

Atlas is governed by Foundation Documents and ADRs; the implementation is meant to follow the architecture. Before large changes, consult `docs/foundation/` (Constitution, data model, scoring model, provider interfaces, roadmap) and `specifications/adr/`. Version notes in `docs/ATLAS_v0_*_NOTES.md` track what each milestone added.
