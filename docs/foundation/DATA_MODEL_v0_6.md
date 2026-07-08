# Atlas Data Model v0.6

## Separation of Concerns

Atlas separates tables into four zones.

## 1. Public Research Zone

Public data that can be refreshed from external sources.

- `asset`
- `fund`
- `fund_holding`
- `company`
- `sector`
- `theme`
- `theme_link`
- `price_history`
- `fund_metadata_snapshot`

## 2. Private Portfolio Zone

Data that should remain local.

- `portfolio`
- `portfolio_position`
- `portfolio_snapshot`
- `account`
- `cash_position`

## 3. Decision Intelligence Zone

Investor reasoning and decision history.

- `decision`
- `thesis`
- `decision_evidence`
- `change_mind_condition`
- `watchlist_item`
- `mistake_log`

## 4. Scoring and Model Zone

Transparent analytical outputs.

- `score_model`
- `score_component`
- `score_result`
- `score_explanation`
- `scenario`
- `scenario_score`

## Current Prototype Compatibility

The current v0.5 tables remain in place for functionality:

- `etf`
- `etf_score`
- `portfolio`
- `portfolio_position`
- `journal_entry`

During Foundation Phase, we will gradually migrate toward the normalized model while preserving the working commands.
