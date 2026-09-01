from __future__ import annotations

import sqlite3
from html import escape
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from atlas.analytics.overlap import holdings_weight_source, top_repeated_holdings, top_ten_holdings
from atlas.application.kernel import ATLAS_VERSION, AtlasKernel
from atlas.plugins.hello import HelloAtlasPlugin
from atlas.db.database import connect, load_seed_universe
from atlas.reports.markdown import build_research_report
from atlas.scoring.engine import read_scores, score_all
from atlas.scoring.model import SCORER_VERSION, format_component

DEFAULT_DB = Path(".atlas/atlas.db")
DEFAULT_SEED = Path("data/atlas_seed_universe.csv")

app = FastAPI(title="Atlas", version="0.8.0")


def _kernel_report() -> dict[str, object]:
    kernel = AtlasKernel.from_environment()
    kernel.register_plugin(HelloAtlasPlugin())
    kernel.start()
    try:
        report = kernel.health_service().report(ready=kernel.started)
        return {
            "status": report.status,
            "ready": report.ready,
            "version": report.version,
            "environment": report.environment,
            "plugins_loaded": report.plugins_loaded,
        }
    finally:
        kernel.shutdown()


@app.get("/health")
def health() -> dict[str, object]:
    return _kernel_report()


@app.get("/ready")
def ready() -> dict[str, object]:
    return _kernel_report()


@app.get("/version")
def version() -> dict[str, str]:
    return {"version": ATLAS_VERSION}


_initialized = False


def _ensure_initialized() -> None:
    """Load the seed universe and score the ETFs once for the app's lifetime.

    Previously every request reloaded the seed CSV and re-ran (and re-wrote)
    the full scoring pass. That work only needs to happen once; request
    handlers now read the persisted results.
    """
    global _initialized
    if _initialized:
        return
    conn = connect(DEFAULT_DB)
    try:
        if DEFAULT_SEED.exists():
            load_seed_universe(conn, DEFAULT_SEED)
        score_all(conn)
    finally:
        conn.close()
    _initialized = True


def _conn() -> sqlite3.Connection:
    _ensure_initialized()
    return connect(DEFAULT_DB)


def _page(title: str, body: str) -> str:
    return f"""
    <!doctype html>
    <html lang="en">
    <head>
      <meta charset="utf-8">
      <meta name="viewport" content="width=device-width, initial-scale=1">
      <title>{escape(title)} — Atlas</title>
      <style>
        body {{ font-family: system-ui, -apple-system, Segoe UI, sans-serif; margin: 2rem; color: #18202a; }}
        header {{ border-bottom: 1px solid #ddd; margin-bottom: 1.5rem; padding-bottom: 1rem; }}
        nav a {{ margin-right: 1rem; }}
        table {{ border-collapse: collapse; width: 100%; margin: 1rem 0; }}
        th, td {{ border-bottom: 1px solid #e5e5e5; padding: .55rem; text-align: left; }}
        th {{ background: #f6f7f9; }}
        .score {{ font-weight: 700; text-align: right; }}
        .muted {{ color: #667; }}
        .card {{ border: 1px solid #ddd; border-radius: .75rem; padding: 1rem; margin: 1rem 0; }}
        code {{ background: #f4f4f4; padding: .15rem .3rem; border-radius: .25rem; }}
      </style>
    </head>
    <body>
      <header>
        <h1>Atlas</h1>
        <p class="muted">Maps, not predictions.</p>
        <nav>
          <a href="/">Dashboard</a>
          <a href="/etfs">ETF Scores</a>
          <a href="/concentration">Repeated Holdings</a>
          <a href="/report">Markdown Report</a>
        </nav>
      </header>
      {body}
    </body>
    </html>
    """


@app.get("/", response_class=HTMLResponse)
def dashboard() -> str:
    conn = _conn()
    etf_count = conn.execute("SELECT COUNT(*) AS count FROM etf").fetchone()["count"]
    # "Scored" means a fund that actually got an overall score. A row in
    # `etf_score` is not the same thing now that a fund with nothing
    # measurable stores its role, its AI heuristic and a NULL score; counting
    # rows would report the whole universe as scored.
    scores = read_scores(conn)
    score_count = sum(1 for score in scores if score.overall_score is not None)
    unscored_count = len(scores) - score_count
    repeated = top_repeated_holdings(conn, limit=5)
    rows = "".join(
        f"<tr><td>{escape(row['holding_symbol'])}</td><td>{row['etf_count']}</td><td>{escape(row['etfs'])}</td></tr>"
        for row in repeated
    )
    body = f"""
      <section class="card">
        <h2>Private Research Dashboard</h2>
        <p>Atlas is running locally and using the SQLite database at <code>{escape(str(DEFAULT_DB))}</code>.</p>
        <p><strong>{etf_count}</strong> ETFs loaded. <strong>{score_count}</strong> ETFs scored, <strong>{unscored_count}</strong> with nothing measurable to score.</p>
      </section>
      <section class="card">
        <h2>Top Repeated Top-Ten Holdings</h2>
        <table><thead><tr><th>Holding</th><th>ETF Count</th><th>ETFs</th></tr></thead><tbody>{rows}</tbody></table>
      </section>
      <section class="card">
        <h2>Next Atlas Milestone</h2>
        <p>Real weighted holdings can now be imported per fund with <code>atlas import-holdings</code>. Next: raise coverage across the universe, and add weighted overlap math, while keeping personal portfolio data private and local.</p>
      </section>
    """
    return _page("Dashboard", body)


@app.get("/etfs", response_class=HTMLResponse)
def etfs(limit: int = Query(50, ge=1, le=200)) -> str:
    conn = _conn()
    # `read_scores` orders unscored funds last, so slicing to `limit` shows the
    # measurable funds first and never has to compare a None.
    all_scores = read_scores(conn)
    scores = all_scores[:limit]
    rows = "".join(
        "<tr>"
        f"<td>{idx}</td>"
        f"<td><a href='/etfs/{escape(score.symbol)}'>{escape(score.symbol)}</a></td>"
        f"<td class='score'>{format_component(score.overall_score)}</td>"
        f"<td>{escape(score.role)}</td>"
        f"<td>{score.ai_score}</td>"
        f"<td>{format_component(score.resilience_score)}</td>"
        f"<td>{format_component(score.cost_score)}</td>"
        f"<td>{format_component(score.diversification_score)}</td>"
        "</tr>"
        for idx, score in enumerate(scores, start=1)
    )
    unscored = sum(1 for score in all_scores if score.overall_score is None)
    unscored_note = (
        f"<p class=\"muted\">{unscored} of {len(all_scores)} funds have no overall score at "
        "all: none of cost, resilience or diversification could be measured, leaving only "
        "the AI keyword heuristic, and Atlas will not build a number out of that. They are "
        "ranked last because there is no basis for ranking them, not because they scored "
        "badly.</p>"
        if unscored
        else ""
    )
    body = f"""
      <h2>ETF Scores</h2>
      <p class="muted">These are {SCORER_VERSION} heuristic scores. Every score remains explainable and subject to refinement. An &mdash; means Atlas did not measure that component: cost needs a gross expense ratio, resilience needs an information-technology exposure figure, and diversification needs an imported holdings file covering the whole fund. An unmeasured component is excluded and the rest share the same budget, so the gap neither helps nor hurts.</p>
      {unscored_note}
      <table>
        <thead><tr><th>Rank</th><th>ETF</th><th>Score</th><th>Role</th><th>AI</th><th>Resilience</th><th>Cost</th><th>Diversification</th></tr></thead>
        <tbody>{rows}</tbody>
      </table>
    """
    return _page("ETF Scores", body)


@app.get("/etfs/{symbol}", response_class=HTMLResponse)
def etf_detail(symbol: str) -> str:
    conn = _conn()
    symbol = symbol.upper()
    score = next((item for item in read_scores(conn) if item.symbol == symbol), None)
    row = conn.execute("SELECT * FROM etf WHERE symbol = ?", (symbol,)).fetchone()
    if score is None or row is None:
        return _page("ETF Not Found", f"<h2>{escape(symbol)} not found</h2>")
    holdings = top_ten_holdings(conn, symbol)
    holding_items = (
        "".join(f"<li>{escape(holding)}</li>" for holding in holdings)
        or "<li>No holdings parsed.</li>"
    )
    holdings_basis = {
        "holdings_file": "Top ten by weight, from an imported holdings file.",
        "seed_top_ten": "Seed select-list top-ten membership; no weights. "
        "Import a holdings file covering the whole fund "
        "(<code>atlas import-holdings</code>) to use its real weights; a "
        "partial export sits alongside this list rather than replacing it.",
    }.get(holdings_weight_source(conn, symbol), "No holdings on file for this fund.")
    # An unscored fund gets a sentence, not "None / 100" and not a dash sitting
    # where a number is expected. The explanation below it says why.
    headline = (
        "<p><strong>Not scored</strong> &mdash; "
        f"{escape(score.role)} (keyword heuristic)</p>"
        if score.overall_score is None
        else f"<p><strong>{score.overall_score}</strong> / 100 &mdash; {escape(score.role)}</p>"
    )
    body = f"""
      <h2>{escape(symbol)} — {escape(row['description'])}</h2>
      <section class="card">
        <h3>Score</h3>
        {headline}
        <p>{escape(score.explanation)}</p>
      </section>
      <section class="card">
        <h3>Seed Facts</h3>
        <p>Category: {escape(row['category'] or '')}</p>
        <p>Expense ratio: {escape(row['gross_expense_ratio'] or 'unknown')}</p>
        <p>Information technology exposure: {escape(row['information_technology_exposure'] or 'unknown')}</p>
      </section>
      <section class="card">
        <h3>Parsed Top-Ten Holdings</h3>
        <p class="muted">{holdings_basis}</p>
        <ol>{holding_items}</ol>
      </section>
    """
    return _page(symbol, body)


@app.get("/concentration", response_class=HTMLResponse)
def concentration(limit: int = Query(30, ge=1, le=100)) -> str:
    conn = _conn()
    rows = top_repeated_holdings(conn, limit=limit)
    table_rows = "".join(
        f"<tr><td>{escape(row['holding_symbol'])}</td><td>{row['etf_count']}</td><td>{escape(row['etfs'])}</td></tr>"
        for row in rows
    )
    body = f"""
      <h2>Repeated Holdings</h2>
      <p class="muted">This is the first hidden-concentration warning system. It counts how many funds hold each name in their top ten &mdash; real top ten by weight where a holdings file covering the whole fund has been imported, seed select-list top ten otherwise. It counts fund membership only and shows no dollar exposure; for dollars, see <code>atlas analyze-portfolio</code>.</p>
      <table><thead><tr><th>Holding</th><th>ETF Count</th><th>ETFs</th></tr></thead><tbody>{table_rows}</tbody></table>
    """
    return _page("Repeated Holdings", body)


@app.get("/report", response_class=PlainTextResponse)
def report() -> str:
    conn = _conn()
    return build_research_report(conn)
