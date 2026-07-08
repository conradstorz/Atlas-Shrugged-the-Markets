# Atlas v0.6.2 — Foundation Phase

Atlas is a private investment decision intelligence platform for long-term investors.

**Motto:** Maps, not predictions.

This v0.6.2 release begins the Foundation Phase. It preserves the working v0.5.1 command-line workflow while adding the architectural documents and core abstractions needed for long-term growth.

## Quick Start

```bash
uv sync
uv run pytest
uv run atlas import-seed --seed data/atlas_seed_universe.csv
uv run atlas score-etfs
uv run atlas serve
```

Open:

```text
http://127.0.0.1:8000
```

## Foundation Documents

- `docs/foundation/ATLAS_CONSTITUTION_v1.md`
- `docs/foundation/FOUNDATION_ARCHITECTURE_v0_6.md`
- `docs/foundation/DATA_MODEL_v0_6.md`
- `docs/foundation/SCORING_MODEL_v0_6.md`
- `docs/foundation/PROVIDER_INTERFACES_v0_6.md`
- `docs/foundation/ROADMAP_FOUNDATION_PHASE.md`

## Working Commands

```bash
uv run atlas import-seed --seed data/atlas_seed_universe.csv
uv run atlas score-etfs
uv run atlas compare-overlap SCHB SCHD
uv run atlas repeat-holdings
uv run atlas import-portfolio examples/sample_portfolio.csv
uv run atlas analyze-portfolio
uv run atlas generate-report
uv run atlas journal-add SCHB --decision watch --thesis "Foundation U.S. market exposure."
uv run atlas journal-list
uv run atlas serve
```

## What Changed in v0.6.2

- Added the Atlas Constitution.
- Added Foundation Phase architecture docs.
- Added initial core abstractions for evidence, explainable scoring, decisions, and themes.
- Added provider interface placeholders so future data sources do not distort the architecture.
- Preserved the working CLI and local FastAPI dashboard.

## What Is Deferred

- Brokerage API connectors
- Authentication
- Cloud sync
- PostgreSQL
- Real-time data
- AI assistant layer

These are intentionally deferred under YAGNI until the local private decision engine is stronger.


## v0.6.2 packaging fix

This release restores the `httpx2` dependency required by the current Starlette/FastAPI TestClient while continuing to omit `uv.lock`, so local installs resolve against the user's normal package index instead of a build-environment mirror.
