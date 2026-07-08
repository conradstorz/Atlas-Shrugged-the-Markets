# Atlas v0.5 Notes

Atlas v0.5 adds the first local web dashboard.

## New command

```bash
uv run atlas serve
```

Then open:

```text
http://127.0.0.1:8000
```

## New web pages

- `/` — private research dashboard
- `/etfs` — ranked ETF scores
- `/etfs/{symbol}` — single ETF detail page
- `/concentration` — repeated holdings prototype
- `/report` — plaintext Markdown research report

## Important limitation

The dashboard still uses the uploaded seed file and parsed top-ten holdings only. It is not yet a full holdings engine. v0.6 should add a formal data-source abstraction so Atlas can ingest complete ETF holdings from provider files while keeping personal portfolio data local.
