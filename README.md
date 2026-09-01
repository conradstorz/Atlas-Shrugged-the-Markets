# Atlas

**Maps, not predictions.**

Atlas is a private decision intelligence platform for long-term investors.

This repository contains the Atlas Kernel — the platform spine of configuration, secrets abstraction, structured logging, plugin lifecycle, and health endpoints — plus the investment layer built on top of it: ETF scoring, weighted fund look-through, portfolio import, a decision journal, and a local dashboard.

## Quick Start

```bash
uv sync
uv run pytest
uv run atlas kernel-check
uv run atlas serve
```

Open:

```text
http://127.0.0.1:8000
```

Health endpoints:

```text
http://127.0.0.1:8000/health
http://127.0.0.1:8000/ready
http://127.0.0.1:8000/version
```

## Kernel Principle

The Kernel intentionally contains no investment logic. It does not know about ETFs, portfolios, scores, or market data. It provides the environment in which those future capabilities will execute.

## Key Commands

```bash
uv run atlas kernel-check
uv run atlas import-seed --seed data/atlas_seed_universe.csv
uv run atlas score-etfs
uv run atlas import-holdings SYMBOL FILE
uv run atlas coverage
uv run atlas serve
```

## Governance

Atlas is governed by its Foundation Documents, Engineering Specifications, Build Specifications, and ADRs. The implementation follows the architecture; the architecture follows the principles.
