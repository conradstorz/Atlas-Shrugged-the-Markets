# Atlas Foundation Architecture v0.6

## Purpose

This release marks the transition from prototype mode to Foundation Phase. The goal is not more features; the goal is an architecture that can support Atlas as a private investment decision intelligence platform.

## Core Entities

Atlas is built around these long-lived concepts:

- **Asset** — anything that can be owned.
- **Fund** — a pooled investment vehicle such as an ETF or mutual fund.
- **Company** — an operating business or issuer.
- **Holding** — an ownership relationship between a portfolio, fund, or company.
- **Portfolio** — a private collection of positions.
- **Theme** — an economic theme such as AI Compute, Power Grid, Dividend Quality, or Interest Rate Sensitivity.
- **Evidence** — a fact or observation used to support a model or decision.
- **Score** — an explainable evaluation derived from components and weights.
- **Decision** — a private investor action or watchlist judgment.
- **Thesis** — the written reason a holding deserves attention or capital.

## Package Boundaries

```text
atlas/
  core/          foundational abstractions: evidence, scoring, decisions, themes
  db/            SQLite connection and schema
  providers/     interfaces for public data and private imports
  scoring/       current ETF scoring implementation
  analytics/     overlap and concentration calculations
  portfolio/     private portfolio analysis
  journal/       decision journal services
  reports/       portable Markdown reports
  web/           local FastAPI dashboard
  cli/           command-line entry points
```

## What Is Not Being Built Yet

- Brokerage API connections
- Multi-user authentication
- Cloud sync
- Mobile app
- PostgreSQL migration
- Real-time market data
- AI assistant layer

These are deferred until the local single-user decision engine is trustworthy.

## Foundation Commitments

1. Keep the command line working at every release.
2. Keep SQLite as the first-class private database.
3. Keep score explanations visible.
4. Keep imports local.
5. Keep public research data separate from private portfolio data.
