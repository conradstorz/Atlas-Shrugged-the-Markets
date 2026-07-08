# Atlas Provider Interfaces v0.6

## Purpose

Provider interfaces are foundation work, not feature work. They prevent Atlas from being tied to one data source.

## Provider Types

- `ResearchDataProvider` — ETF metadata, expenses, holdings, sectors.
- `PriceDataProvider` — historical prices and distributions.
- `PortfolioImportProvider` — brokerage CSV imports.
- `ClassificationProvider` — sector, industry, and theme mapping.

## v0.6 Implementations

Only manual CSV import exists today. Other providers are interfaces and placeholders.

## Deferred Providers

- Schwab brokerage connector
- Fidelity brokerage connector
- SEC data provider
- Yahoo-style price provider
- Morningstar-style category provider

These remain out of scope until the local model is stable.
