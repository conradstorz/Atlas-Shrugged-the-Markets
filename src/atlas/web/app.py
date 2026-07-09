from __future__ import annotations

import sqlite3
from html import escape
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.responses import HTMLResponse, PlainTextResponse

from atlas.analytics.overlap import top_repeated_holdings
from atlas.application.kernel import ATLAS_VERSION, AtlasKernel
from atlas.plugins.hello import HelloAtlasPlugin
from atlas.db.database import connect, load_seed_universe
from atlas.reports.markdown import build_research_report
from atlas.scoring.engine import read_scores, score_all

DEFAULT_DB = Path(".atlas/atlas.db")
DEFAULT_SEED = Path("data/atlas_seed_universe.csv")

app = FastAPI(title="Atlas", version="0.7.0")


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
    score_count = len(read_scores(conn))
    repeated = top_repeated_holdings(conn, limit=5)
    rows = "".join(
        f"<tr><td>{escape(row['holding_symbol'])}</td><td>{row['etf_count']}</td><td>{escape(row['etfs'])}</td></tr>"
        for row in repeated
    )
    body = f"""
      <section class="card">
        <h2>Private Research Dashboard</h2>
        <p>Atlas is running locally and using the SQLite database at <code>{escape(str(DEFAULT_DB))}</code>.</p>
        <p><strong>{etf_count}</strong> ETFs loaded. <strong>{score_count}</strong> ETFs scored.</p>
      </section>
      <section class="card">
        <h2>Top Repeated Seed Holdings</h2>
        <table><thead><tr><th>Holding</th><th>ETF Count</th><th>ETFs</th></tr></thead><tbody>{rows}</tbody></table>
      </section>
      <section class="card">
        <h2>Next Atlas Milestone</h2>
        <p>Replace seed top-ten holdings with full holdings from public data sources, while keeping personal portfolio data private and local.</p>
      </section>
    """
    return _page("Dashboard", body)


@app.get("/etfs", response_class=HTMLResponse)
def etfs(limit: int = Query(50, ge=1, le=200)) -> str:
    conn = _conn()
    scores = read_scores(conn)[:limit]
    rows = "".join(
        "<tr>"
        f"<td>{idx}</td>"
        f"<td><a href='/etfs/{escape(score.symbol)}'>{escape(score.symbol)}</a></td>"
        f"<td class='score'>{score.overall_score}</td>"
        f"<td>{escape(score.role)}</td>"
        f"<td>{score.ai_score}</td>"
        f"<td>{score.resilience_score}</td>"
        f"<td>{score.cost_score}</td>"
        f"<td>{score.diversification_score}</td>"
        "</tr>"
        for idx, score in enumerate(scores, start=1)
    )
    body = f"""
      <h2>ETF Scores</h2>
      <p class="muted">These are v0.5 heuristic scores. Every score remains explainable and subject to refinement.</p>
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
    holdings = conn.execute(
        "SELECT holding_symbol FROM etf_holding WHERE etf_symbol = ? ORDER BY rank", (symbol,)
    ).fetchall()
    holding_items = "".join(f"<li>{escape(h['holding_symbol'])}</li>" for h in holdings) or "<li>No seed holdings parsed.</li>"
    body = f"""
      <h2>{escape(symbol)} — {escape(row['description'])}</h2>
      <section class="card">
        <h3>Score</h3>
        <p><strong>{score.overall_score}</strong> / 100 — {escape(score.role)}</p>
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
      <p class="muted">This is the first hidden-concentration warning system. It currently uses only parsed seed top-ten holdings.</p>
      <table><thead><tr><th>Holding</th><th>ETF Count</th><th>ETFs</th></tr></thead><tbody>{table_rows}</tbody></table>
    """
    return _page("Repeated Holdings", body)


@app.get("/report", response_class=PlainTextResponse)
def report() -> str:
    conn = _conn()
    return build_research_report(conn)
