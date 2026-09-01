from __future__ import annotations

import sqlite3
from datetime import datetime
from pathlib import Path

from atlas.analytics.overlap import top_repeated_holdings
from atlas.portfolio.analysis import combined_concentration, summarize_portfolio
from atlas.scoring.engine import score_all
from atlas.scoring.model import SCORER_VERSION


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
        f"These scores are still {SCORER_VERSION} heuristic scores. They are useful for building the explainable workflow, not for pretending the model is finished.",
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
        "## Most Repeated Top-Ten Holdings",
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
            "### Coverage",
            "",
            "The number that governs whether the table below can be trusted: how "
            "much of this portfolio's dollars are actually modeled.",
            "",
        ])
        concentration_limit = 25
        report_data = combined_concentration(conn, portfolio_name, limit=concentration_limit)
        modeled_percent = (
            round(report_data.modeled_value / report_data.total_value * 100, 2)
            if report_data.total_value
            else 0.0
        )
        lines.extend([
            f"Modeled: {_money(report_data.modeled_value)} of "
            f"{_money(report_data.total_value)} ({modeled_percent:.2f}%).",
            "",
            "| Component | Value |",
            "|---|---:|",
            f"| Modeled (direct + weighted look-through) | {_money(report_data.modeled_value)} |",
            f"| Unmodeled fund value | {_money(report_data.unmodeled_fund_value)} |",
            f"| Cash | {_money(report_data.cash_value)} |",
            f"| Other | {_money(report_data.other_value)} |",
            f"| Total | {_money(report_data.total_value)} |",
            "",
            "#### Per-Fund Coverage",
            "",
            "Funds without real weights (Has Weights: No) are the actionable list — "
            "run `atlas import-holdings SYMBOL FILE` for each to raise coverage.",
            "",
            "| Fund | Market Value | Has Weights | Modeled Share | Modeled Value |",
            "|---|---:|---|---:|---:|",
        ])
        for fc in report_data.fund_coverage:
            lines.append(
                f"| {fc.symbol} | {_money(fc.market_value)} | {'Yes' if fc.has_weights else 'No'} | "
                f"{fc.modeled_share * 100:.2f}% | {_money(fc.modeled_value)} |"
            )
        # Only claim truncation when truncation actually happened.
        # `combined_concentration` trims to `limit`, so a full-length table is
        # the only truncation signal available. Deriving a "remaining" figure by
        # subtracting the visible rows from `modeled_value` would be exactly the
        # kind of unsupported number this caveat exists to prevent — as would
        # announcing "the top 0 names" above an empty table, which is what
        # `len(report_data.lines)` produced in the shipped, nothing-imported
        # state. A modeled set that lands on precisely `limit` names prints the
        # caveat unnecessarily; that false positive is far cheaper than a reader
        # mistaking a partial table for the whole one.
        truncation_note = (
            f" The table below shows the top {concentration_limit} names by exposure; "
            "it is not the full modeled set (see the Coverage dollar totals above for that)."
            if len(report_data.lines) == concentration_limit
            else ""
        )
        lines.extend([
            "",
            "### Combined Concentration",
            "",
            "Per-name exposure combining directly-held positions with weighted "
            "ETF/fund look-through. Both direct dollars and weighted look-through "
            "are exact math, not estimates. Fund value without an imported "
            "holdings file is excluded from this table rather than estimated — "
            "see Coverage above for how much that is." + truncation_note,
            "",
            "| Symbol | Exposure % | Exposure | Direct | Look-through | Source Funds |",
            "|---|---:|---:|---:|---:|---|",
        ])
        for line in report_data.lines:
            lines.append(
                f"| {line.symbol} | {line.exposure_percent:.2f}% | {_money(line.exposure_value)} | "
                f"{_money(line.direct_value)} | {_money(line.lookthrough_value)} | "
                f"{', '.join(line.source_funds) or '-'} |"
            )

    lines.extend([
        "",
        "## Current Limitations",
        "",
        "- Holdings weights are used for look-through only where a fund's holdings file "
        "has been imported (`atlas import-holdings`); a fund without one is excluded "
        "from look-through entirely, not estimated.",
        "- The seed universe's top-ten select-list carries fund membership only, with "
        "no weights — it is never enough on its own to model a fund.",
        "- Valuation, dividend growth, historical volatility, and drawdown data are not yet connected.",
        "- Scores are explainable but still early heuristics.",
        "",
        "## Next Model Improvements",
        "",
        "1. Import holdings files for the rest of the ETF universe to raise weighted coverage.",
        "2. Add weighted overlap math to `compare-overlap` (it still compares top-ten membership only).",
        "3. Add score profiles so different investment philosophies can be compared.",
        "4. Add scenario scoring for AI acceleration, AI disappointment, persistent inflation, and broadening market leadership.",
    ])
    return "\n".join(lines) + "\n"


def write_research_report(conn: sqlite3.Connection, output_path: Path, portfolio_name: str | None = None) -> Path:
    """Write an Atlas Markdown report and return the output path."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(build_research_report(conn, portfolio_name=portfolio_name), encoding="utf-8")
    return output_path
