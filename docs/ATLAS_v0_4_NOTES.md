# Atlas v0.4 Notes

## Objective

Atlas v0.4 moves the project from command-line diagnostics toward a practical private research workflow.

The milestone question is:

> Can Atlas produce a portable, readable report and preserve the reasoning behind a decision?

## New Capabilities

- Generates a Markdown research report.
- Includes ETF scores and repeated top-ten holdings.
- Optionally includes a private portfolio summary and hidden concentration prototype.
- Adds the first decision journal service.
- Adds CLI commands for creating and listing journal entries.
- Adds an example private portfolio CSV.

## New Commands

```bash
uv run atlas generate-report --output reports/atlas_research_report.md
uv run atlas import-portfolio examples/sample_portfolio.csv --name Primary
uv run atlas generate-report --portfolio-name Primary --output reports/atlas_primary_report.md
uv run atlas journal-add SCHB --decision watch --thesis "Core broad-market U.S. exposure" --confidence 95
uv run atlas journal-list
```

## Design Importance

The report command is important because it establishes a pattern:

1. collect facts,
2. run explainable models,
3. produce a readable artifact,
4. store the reasoning.

That is the core Atlas loop.

## Still Not Done

Atlas still needs:

- full holdings ingestion,
- actual holding weights,
- current ETF metadata refresh,
- price history,
- valuation data,
- scenario scoring,
- Docker deployment,
- web UI.

## Next Target: v0.5

Atlas v0.5 should add a Docker-first local deployment and the first FastAPI/HTMX dashboard skeleton.
