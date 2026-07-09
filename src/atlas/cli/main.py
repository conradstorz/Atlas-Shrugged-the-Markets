from __future__ import annotations

from pathlib import Path

import typer
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

from atlas.analytics.overlap import compare_etfs, top_repeated_holdings
from atlas.db.database import connect, load_portfolio_csv, load_seed_universe
from atlas.journal.service import add_journal_entry, list_journal_entries
from atlas.portfolio.analysis import combined_concentration, summarize_portfolio
from atlas.portfolio.schwab import load_schwab_positions
from atlas.reports.markdown import write_research_report
from atlas.scoring.engine import score_all

app = typer.Typer(help="Atlas private investment decision intelligence CLI.")
console = Console()


@app.command("import-seed")
def import_seed(
    seed: Path = typer.Option(Path("data/atlas_seed_universe.csv"), help="Seed ETF universe CSV."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
) -> None:
    """Load the ETF seed universe into the local Atlas database."""
    conn = connect(db)
    loaded = load_seed_universe(conn, seed)
    console.print(f"Loaded {loaded} ETFs into {db}")


@app.command("score-etfs")
def score_etfs(
    seed: Path = typer.Option(Path("data/atlas_seed_universe.csv"), help="Seed ETF universe CSV."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
    limit: int = typer.Option(25, help="Number of ranked ETFs to display."),
) -> None:
    """Load the seed universe and print v0.4 explainable ETF scores."""
    conn = connect(db)
    loaded = load_seed_universe(conn, seed)
    scores = score_all(conn)

    table = Table(title=f"Atlas ETF Scores v0.4 — {loaded} ETFs loaded")
    table.add_column("Rank", justify="right")
    table.add_column("ETF")
    table.add_column("Score", justify="right")
    table.add_column("Role")
    table.add_column("AI", justify="right")
    table.add_column("Resilience", justify="right")
    table.add_column("Cost", justify="right")
    table.add_column("Diversification", justify="right")

    for rank, score in enumerate(scores[:limit], start=1):
        table.add_row(
            str(rank),
            score.symbol,
            str(score.overall_score),
            score.role,
            str(score.ai_score),
            str(score.resilience_score),
            str(score.cost_score),
            str(score.diversification_score),
        )

    console.print(table)
    console.print("\nThis is still a heuristic scoring pass. Full holdings and valuation enrichment come next.")


@app.command("compare-overlap")
def compare_overlap(
    left_symbol: str = typer.Argument(..., help="First ETF ticker."),
    right_symbol: str = typer.Argument(..., help="Second ETF ticker."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
) -> None:
    """Compare top-ten holdings overlap between two ETFs."""
    conn = connect(db)
    result = compare_etfs(conn, left_symbol, right_symbol)
    table = Table(title=f"Top-Ten Holdings Overlap: {result.left_symbol} vs {result.right_symbol}")
    table.add_column("Metric")
    table.add_column("Value")
    table.add_row("Shared holdings", str(result.shared_count))
    table.add_row(f"{result.left_symbol} parsed holdings", str(result.left_count))
    table.add_row(f"{result.right_symbol} parsed holdings", str(result.right_count))
    table.add_row("Jaccard overlap", f"{result.jaccard_percent}%")
    table.add_row("Shared symbols", ", ".join(result.shared_symbols) or "None")
    console.print(table)


@app.command("repeat-holdings")
def repeat_holdings(
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
    limit: int = typer.Option(20, help="Number of repeated holdings to show."),
) -> None:
    """Show companies appearing most often across ETF top-ten lists."""
    conn = connect(db)
    rows = top_repeated_holdings(conn, limit=limit)
    table = Table(title="Most Repeated Seed Holdings")
    table.add_column("Holding")
    table.add_column("ETF Count", justify="right")
    table.add_column("ETFs")
    for row in rows:
        table.add_row(row["holding_symbol"], str(row["etf_count"]), row["etfs"])
    console.print(table)


@app.command("import-portfolio")
def import_portfolio(
    portfolio_csv: Path = typer.Argument(..., help="Private portfolio CSV path."),
    name: str = typer.Option("Primary", help="Portfolio name."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
) -> None:
    """Import a private portfolio CSV into the local database."""
    conn = connect(db)
    count = load_portfolio_csv(conn, name, portfolio_csv)
    summary = summarize_portfolio(conn, name)
    console.print(f"Imported {count} positions into portfolio '{summary.name}'.")
    console.print(f"Total value: ${summary.total_value:,.2f}")


@app.command("import-schwab")
def import_schwab(
    positions_csv: Path = typer.Argument(..., help="Schwab Positions CSV export."),
    name: str = typer.Option("Primary", help="Portfolio name."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
) -> None:
    """Import a Charles Schwab Positions CSV export."""
    conn = connect(db)
    count = load_schwab_positions(conn, name, positions_csv)
    summary = summarize_portfolio(conn, name)
    console.print(f"Imported {count} Schwab positions into portfolio '{summary.name}'.")
    console.print(
        f"Total: ${summary.total_value:,.2f} — equity ${summary.equity_value:,.2f}, "
        f"funds ${summary.fund_value:,.2f}, cash ${summary.cash_value:,.2f}"
    )


@app.command("analyze-portfolio")
def analyze_portfolio(
    name: str = typer.Option("Primary", help="Portfolio name."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
    limit: int = typer.Option(20, help="Number of hidden concentration rows."),
) -> None:
    """Summarize a private portfolio and estimate hidden top-ten concentration."""
    conn = connect(db)
    summary = summarize_portfolio(conn, name)
    console.print(f"[bold]Portfolio:[/bold] {summary.name}")
    console.print(f"Positions: {summary.position_count}")
    console.print(
        f"Total value: ${summary.total_value:,.2f} — equity ${summary.equity_value:,.2f}, "
        f"funds ${summary.fund_value:,.2f}, cash ${summary.cash_value:,.2f}"
    )

    report = combined_concentration(conn, name, limit=limit)
    table = Table(title="Combined Concentration (Direct + ETF/Fund Look-Through)")
    table.add_column("Symbol")
    table.add_column("Exposure %", justify="right")
    table.add_column("Exposure", justify="right")
    table.add_column("Direct", justify="right")
    table.add_column("Look-through", justify="right")
    table.add_column("Source Funds")
    for line in report.lines:
        table.add_row(
            line.symbol,
            f"{line.exposure_percent:.2f}%",
            f"${line.exposure_value:,.2f}",
            f"${line.direct_value:,.2f}",
            f"${line.lookthrough_value:,.2f}",
            ", ".join(line.source_funds) or "-",
        )
    console.print(table)
    console.print(f"\nFund value not looked through: ${report.unmodeled_fund_value:,.2f}")
    console.print(
        "Note: look-through uses the equal-weight top-ten prototype; direct holdings are exact."
    )


@app.command("generate-report")
def generate_report(
    seed: Path = typer.Option(Path("data/atlas_seed_universe.csv"), help="Seed ETF universe CSV."),
    output: Path = typer.Option(Path("reports/atlas_research_report.md"), help="Markdown report output path."),
    portfolio_name: str | None = typer.Option(None, help="Optional private portfolio name to include."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
) -> None:
    """Generate a portable Markdown Atlas research report."""
    conn = connect(db)
    load_seed_universe(conn, seed)
    report_path = write_research_report(conn, output, portfolio_name=portfolio_name)
    console.print(f"Wrote report: {report_path}")


@app.command("journal-add")
def journal_add(
    symbol: str = typer.Argument(..., help="ETF or holding ticker."),
    decision: str = typer.Option(..., help="Decision made, e.g. buy, watch, avoid, trim."),
    thesis: str = typer.Option(..., help="Why this deserves capital or attention."),
    confidence: int | None = typer.Option(None, help="0-100 confidence score."),
    max_allocation_percent: float | None = typer.Option(None, help="Maximum intended allocation percent."),
    change_mind_conditions: str | None = typer.Option(None, help="What evidence would change your mind."),
    notes: str | None = typer.Option(None, help="Additional private notes."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
) -> None:
    """Add a private investment decision journal entry."""
    conn = connect(db)
    entry_id = add_journal_entry(
        conn,
        symbol=symbol,
        decision=decision,
        thesis=thesis,
        confidence=confidence,
        max_allocation_percent=max_allocation_percent,
        change_mind_conditions=change_mind_conditions,
        notes=notes,
    )
    console.print(f"Added journal entry #{entry_id} for {symbol.upper()}.")


@app.command("journal-list")
def journal_list(
    symbol: str | None = typer.Option(None, help="Filter by symbol."),
    limit: int = typer.Option(20, help="Maximum entries to show."),
    db: Path = typer.Option(Path(".atlas/atlas.db"), help="SQLite database path."),
) -> None:
    """Show recent private investment journal entries."""
    conn = connect(db)
    entries = list_journal_entries(conn, symbol=symbol, limit=limit)
    if not entries:
        console.print("No journal entries found.")
        return
    for entry in entries:
        text = (
            f"[bold]{entry.symbol}[/bold] — {entry.decision}\n"
            f"Date: {entry.entry_date}\n"
            f"Confidence: {entry.confidence if entry.confidence is not None else 'not set'}\n"
            f"Max allocation: {entry.max_allocation_percent if entry.max_allocation_percent is not None else 'not set'}\n\n"
            f"Thesis:\n{entry.thesis}\n"
        )
        if entry.change_mind_conditions:
            text += f"\nChange-mind conditions:\n{entry.change_mind_conditions}\n"
        if entry.notes:
            text += f"\nNotes:\n{entry.notes}\n"
        console.print(Panel(text, title=f"Journal #{entry.id}"))


@app.command("kernel-check")
def kernel_check() -> None:
    """Start and stop the Atlas Kernel without loading investment logic."""
    from atlas.application.kernel import AtlasKernel
    from atlas.plugins.hello import HelloAtlasPlugin

    kernel = AtlasKernel.from_environment()
    kernel.register_plugin(HelloAtlasPlugin())
    kernel.start()
    report = kernel.health_service().report(ready=kernel.started)
    console.print(f"Atlas Kernel {report.version} ready: {report.ready}; plugins loaded: {report.plugins_loaded}")
    kernel.shutdown()


@app.command("serve")
def serve(
    host: str = typer.Option("127.0.0.1", help="Web server host."),
    port: int = typer.Option(8000, help="Web server port."),
) -> None:
    """Run the local Atlas FastAPI dashboard."""
    import uvicorn

    uvicorn.run("atlas.web.app:app", host=host, port=port, reload=False)


if __name__ == "__main__":
    app()
