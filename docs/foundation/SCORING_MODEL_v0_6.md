# Atlas Explainable Scoring Model v0.6

## Principle

A score is not a truth. A score is an organized opinion built from evidence, weights, and assumptions.

## Score Shape

Each score should contain:

- `subject_id`
- `score_model_id`
- `overall_score`
- `component_scores`
- `weights`
- `raw_inputs`
- `explanation`
- `confidence`
- `created_at`

## Initial Components

- AI participation
- Downside resilience
- Diversification
- Cost efficiency
- Valuation discipline
- Income quality
- Liquidity
- Simplicity
- Sleep Well score

## Design Rule

No score may be stored without an explanation. If a component is estimated, Atlas must label it as estimated.
