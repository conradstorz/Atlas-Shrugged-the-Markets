from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from atlas.analytics.overlap import top_repeated_holdings
from atlas.portfolio.analysis import combined_concentration, summarize_portfolio
from atlas.scoring.engine import score_all


def _money(value: float) -> str:
    return f"${value:,.2f}"


def build_research_report(conn: sqlite3.Connection, portfolio_name: str | None = None) -> str:
    """Build a readable Markdown report from the current Atlas database.

    The report is intentionally static and portable. It can be committed to a
    private repo, printed, or attached to a decision journal entry.
    """
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    lines: list[str] = [
        "# Atlas Research Report",
        "",
        f"Generated: {now}",
        "",
        "> Maps, not predictions.",
        "",
        "## ETF Scoreboard",
        "",
        "These scores are still v0.4 heuristic scores. They are useful for building the explainable workflow, not for pretending the model is finished.",
        "",
        "| Rank | ETF | Score | Role | AI | Resilience | Cost | Diversification |",
        "|---:|---|---:|---|---:|---:|---:|---:|",
    ]

    scores = score_all(conn)
    for rank, score in enumerate(scores[:40], start=1):
        lines.append(
            f"| {rank} | {score.symbol} | {score.overall_score} | {score.role} | "
            f"{score.ai_score} | {score.resilience_score} | {score.cost_score} | {score.diversification_score} |"
        )

    lines.extend([
        "",
        "## Most Repeated Seed Holdings",
        "",
        "This section shows companies appearing repeatedly in ETF top-ten lists. It is the first warning system for hidden concentration.",
        "",
        "| Holding | ETF Count | ETFs |",
        "|---|---:|---|",
    ])
    for row in top_repeated_holdings(conn, limit=25):
        lines.append(f"| {row['holding_symbol']} | {row['etf_count']} | {row['etfs']} |")

    if portfolio_name:
        summary = summarize_portfolio(conn, portfolio_name)
        lines.extend([
            "",
            f"## Portfolio: {summary.name}",
            "",
            f"- Positions: {summary.position_count}",
            f"- Total value: {_money(summary.total_value)}",
            f"- Equity value: {_money(summary.equity_value)}",
            f"- Fund value (ETF + mutual): {_money(summary.fund_value)}",
            f"- Cash value: {_money(summary.cash_value)}",
            "",
            "### Combined Concentration",
            "",
            "Per-name exposure combining directly-held positions with equal-weight "
            "ETF/fund look-through. Direct dollars are exact; look-through is a "
            "prototype estimate from parsed top-ten holdings.",
            "",
            "| Symbol | Exposure % | Exposure | Direct | Look-through | Source Funds |",
            "|---|---:|---:|---:|---:|---|",
        ])
        report_data = combined_concentration(conn, portfolio_name, limit=25)
        for line in report_data.lines:
            lines.append(
                f"| {line.symbol} | {line.exposure_percent:.2f}% | {_money(line.exposure_value)} | "
                f"{_money(line.direct_value)} | {_money(line.lookthrough_value)} | "
                f"{', '.join(line.source_funds) or '-'} |"
            )
        lines.append("")
        lines.append(f"Fund value not looked through: {_money(report_data.unmodeled_fund_value)}.")

    lines.extend([
        "",
        "## Current Limitations",
        "",
        "- Full holdings are not yet imported.",
        "- Top-ten holdings do not include actual holding weights in the seed file.",
        "- Valuation, dividend growth, historical volatility, and drawdown data are not yet connected.",
        "- Scores are explainable but still early heuristics.",
        "",
        "## Next Model Improvements",
        "",
        "1. Add full holdings ingestion.",
        "2. Add weighted overlap math.",
        "3. Add score profiles so different investment philosophies can be compared.",
        "4. Add scenario scoring for AI acceleration, AI disappointment, persistent inflation, and broadening market leadership.",
    ])
    return "\n".join(lines) + "\n"


def write_research_report(conn: sqlite3.Connection, output_path: Path, portfolio_name: str | None = None) -> Path:
    """Write an Atlas Markdown report and return the output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_research_report(conn, portfolio_name=portfolio_name), encoding="utf-8")
    return output_path
