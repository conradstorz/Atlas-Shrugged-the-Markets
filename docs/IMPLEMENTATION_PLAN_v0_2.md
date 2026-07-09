# Atlas Implementation Plan v0.2

## Objective

Atlas v0.2 turns the project from a philosophy document into a runnable private tool.
The immediate goal is modest but important:

1. Load the seed ETF universe.
2. Store it in SQLite.
3. Produce a first transparent ETF score.
4. Keep the scoring logic isolated so it can be improved without changing the database or UI.

## First Working Command

```bash
uv run atlas score-etfs --seed data/atlas_seed_universe.csv
```

Expected behavior:

- Creates `.atlas/atlas.db` if it does not exist.
- Creates the initial schema.
- Loads ETF seed data.
- Calculates v0.2 scores.
- Prints a ranked table.

## Project Structure

```text
atlas/
  data/                         Seed and local research data
  docs/                         Design and implementation documents
  src/atlas/db/                 SQLite connection, schema, loaders
  src/atlas/scoring/            Explainable scoring engine
  src/atlas/cli/                Command-line entry points
  tests/                        TDD test suite
```

## v0.2 Scope

Included:

- Python package using `uv`.
- SQLite schema for ETF facts and ETF scores.
- CSV loader for the uploaded ETF seed universe.
- First-pass heuristic scoring.
- CLI command to rank ETFs.
- Initial pytest coverage.

Not included yet:

- Live holdings refresh.
- Price history.
- Sector and issuer enrichment.
- Portfolio import.
- Overlap engine.
- Web UI.
- Authentication.
- Docker deployment.

## Scoring Status

The v0.2 scorer is intentionally simple. It uses available fields from the seed ETF list:

- ETF category
- Description
- Gross expense ratio
- Information technology exposure, when present

The purpose is to establish the explainable-scoring workflow. It is not yet the final investment model.

## v0.3 Target

Atlas v0.3 should add public ETF data enrichment:

- Current expense ratios
- Fund sponsor
- Inception date
- AUM
- Holdings
- Sector weights
- Style/category
- Price history

After v0.3, Atlas can begin true overlap and concentration analysis.

## Core Design Rule

Every score must remain explainable. If Atlas shows a number, the user should be able to trace it back to facts, model assumptions, and weighting choices.
