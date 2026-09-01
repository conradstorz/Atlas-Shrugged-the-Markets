from __future__ import annotations

import sqlite3
from dataclasses import dataclass


@dataclass(frozen=True)
class PortfolioSummary:
    name: str
    position_count: int
    total_value: float
    equity_value: float
    fund_value: float
    cash_value: float


def summarize_portfolio(conn: sqlite3.Connection, portfolio_name: str) -> PortfolioSummary:
    portfolio = conn.execute("SELECT id, name FROM portfolio WHERE name = ?", (portfolio_name,)).fetchone()
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_name}")
    row = conn.execute(
        """
        SELECT
            COUNT(*) AS position_count,
            COALESCE(SUM(market_value), 0) AS total_value,
            COALESCE(SUM(CASE WHEN asset_type = 'equity' THEN market_value ELSE 0 END), 0) AS equity_value,
            COALESCE(SUM(CASE WHEN asset_type IN ('etf', 'mutual_fund') THEN market_value ELSE 0 END), 0) AS fund_value,
            COALESCE(SUM(CASE WHEN asset_type = 'cash' THEN market_value ELSE 0 END), 0) AS cash_value
        FROM portfolio_position
        WHERE portfolio_id = ?
        """,
        (portfolio["id"],),
    ).fetchone()
    return PortfolioSummary(
        name=portfolio["name"],
        position_count=int(row["position_count"]),
        total_value=float(row["total_value"]),
        equity_value=float(row["equity_value"]),
        fund_value=float(row["fund_value"]),
        cash_value=float(row["cash_value"]),
    )


@dataclass(frozen=True)
class ConcentrationLine:
    symbol: str
    exposure_value: float
    exposure_percent: float
    direct_value: float
    lookthrough_value: float
    source_funds: list[str]


@dataclass(frozen=True)
class FundCoverage:
    """How much of a fund position's value Atlas can actually see through.

    ``has_weights`` is true only when the fund has real weighted holdings
    (``etf_holding.source = 'holdings_file'``); a seed-only top-ten list is
    membership without weights and is never enough to model a fund.
    """

    symbol: str
    market_value: float
    has_weights: bool
    modeled_share: float
    modeled_value: float


@dataclass(frozen=True)
class ConcentrationReport:
    lines: list[ConcentrationLine]
    total_value: float
    modeled_value: float
    unmodeled_fund_value: float
    cash_value: float
    other_value: float
    fund_coverage: list[FundCoverage]


def _empty_report() -> ConcentrationReport:
    return ConcentrationReport(
        lines=[],
        total_value=0.0,
        modeled_value=0.0,
        unmodeled_fund_value=0.0,
        cash_value=0.0,
        other_value=0.0,
        fund_coverage=[],
    )


@dataclass(frozen=True)
class UniverseCoverage:
    """How much of the entire ``etf`` universe Atlas can see through.

    Every fund in ``etf`` falls into exactly one of three buckets, so the
    three subcategories always sum to ``total_funds``:

    - ``weighted_funds``: has at least one ``etf_holding`` row with
      ``source = 'holdings_file'`` (real weights, from ``atlas import-holdings``).
    - ``membership_only_funds``: has ``etf_holding`` rows, but none of them
      are weighted — a seed top-ten membership list only.
    - ``no_holdings_funds``: has no ``etf_holding`` rows at all.
    """

    total_funds: int
    weighted_funds: int
    membership_only_funds: int
    no_holdings_funds: int


def universe_coverage(conn: sqlite3.Connection) -> UniverseCoverage:
    """Partition every fund in the ``etf`` table by how much Atlas can model it.

    This is a universe-wide count, independent of any portfolio: it answers
    "how much of what Atlas knows about is actually weighted" rather than
    "how much of my money is modeled" (that is ``fund_coverage`` on a
    ``ConcentrationReport``).
    """
    total_funds = int(conn.execute("SELECT COUNT(*) AS c FROM etf").fetchone()["c"])
    weighted_funds = int(
        conn.execute(
            """
            SELECT COUNT(*) AS c FROM etf e
            WHERE EXISTS (
                SELECT 1 FROM etf_holding h
                WHERE h.etf_symbol = e.symbol AND h.source = 'holdings_file'
            )
            """
        ).fetchone()["c"]
    )
    membership_only_funds = int(
        conn.execute(
            """
            SELECT COUNT(*) AS c FROM etf e
            WHERE EXISTS (SELECT 1 FROM etf_holding h WHERE h.etf_symbol = e.symbol)
              AND NOT EXISTS (
                  SELECT 1 FROM etf_holding h
                  WHERE h.etf_symbol = e.symbol AND h.source = 'holdings_file'
              )
            """
        ).fetchone()["c"]
    )
    no_holdings_funds = int(
        conn.execute(
            """
            SELECT COUNT(*) AS c FROM etf e
            WHERE NOT EXISTS (SELECT 1 FROM etf_holding h WHERE h.etf_symbol = e.symbol)
            """
        ).fetchone()["c"]
    )
    return UniverseCoverage(
        total_funds=total_funds,
        weighted_funds=weighted_funds,
        membership_only_funds=membership_only_funds,
        no_holdings_funds=no_holdings_funds,
    )


def combined_concentration(
    conn: sqlite3.Connection, portfolio_name: str, limit: int = 25
) -> ConcentrationReport:
    """Estimate per-name exposure combining direct holdings and fund look-through.

    Direct ``equity`` positions contribute their full market value; that math
    is exact. ``etf`` and ``mutual_fund`` positions look through to their
    ``etf_holding`` rows: where a fund has real weighted holdings
    (``source = 'holdings_file'``), each holding receives
    ``market_value * weight / 100`` and the fund's modeled share is
    ``SUM(weight) / 100``. Any remainder — including the entire value of a
    fund with only unweighted seed top-ten membership rows, or no holdings at
    all — is reported as ``unmodeled_fund_value`` rather than estimated.
    Atlas never spreads a fund's value equally across an unweighted list.
    """
    portfolio = conn.execute(
        "SELECT id FROM portfolio WHERE name = ?", (portfolio_name,)
    ).fetchone()
    if portfolio is None:
        raise ValueError(f"Portfolio not found: {portfolio_name}")
    portfolio_id = portfolio["id"]

    total_value = float(
        conn.execute(
            "SELECT COALESCE(SUM(market_value), 0) AS total FROM portfolio_position WHERE portfolio_id = ?",
            (portfolio_id,),
        ).fetchone()["total"]
    )
    if total_value <= 0:
        return _empty_report()

    direct: dict[str, float] = {}
    for row in conn.execute(
        "SELECT symbol, market_value FROM portfolio_position "
        "WHERE portfolio_id = ? AND asset_type = 'equity'",
        (portfolio_id,),
    ):
        direct[row["symbol"]] = direct.get(row["symbol"], 0.0) + float(row["market_value"])

    cash_value = float(
        conn.execute(
            "SELECT COALESCE(SUM(market_value), 0) AS total FROM portfolio_position "
            "WHERE portfolio_id = ? AND asset_type = 'cash'",
            (portfolio_id,),
        ).fetchone()["total"]
    )
    other_value = float(
        conn.execute(
            "SELECT COALESCE(SUM(market_value), 0) AS total FROM portfolio_position "
            "WHERE portfolio_id = ? AND asset_type NOT IN ('equity', 'etf', 'mutual_fund', 'cash')",
            (portfolio_id,),
        ).fetchone()["total"]
    )

    lookthrough: dict[str, float] = {}
    sources: dict[str, set[str]] = {}
    fund_coverage: list[FundCoverage] = []
    unmodeled_fund_value = 0.0

    funds = conn.execute(
        "SELECT symbol, market_value FROM portfolio_position "
        "WHERE portfolio_id = ? AND asset_type IN ('etf', 'mutual_fund')",
        (portfolio_id,),
    ).fetchall()
    for fund in funds:
        fund_symbol = fund["symbol"]
        fund_value = float(fund["market_value"])
        weighted_holdings = conn.execute(
            "SELECT holding_symbol, weight FROM etf_holding "
            "WHERE etf_symbol = ? AND source = 'holdings_file' AND weight IS NOT NULL",
            (fund_symbol,),
        ).fetchall()

        if weighted_holdings:
            modeled_share = sum(float(h["weight"]) for h in weighted_holdings) / 100.0
            modeled_value = fund_value * modeled_share
            for holding in weighted_holdings:
                symbol = holding["holding_symbol"]
                contribution = fund_value * float(holding["weight"]) / 100.0
                lookthrough[symbol] = lookthrough.get(symbol, 0.0) + contribution
                sources.setdefault(symbol, set()).add(fund_symbol)
            unmodeled_fund_value += fund_value - modeled_value
            fund_coverage.append(
                FundCoverage(
                    symbol=fund_symbol,
                    market_value=round(fund_value, 2),
                    has_weights=True,
                    modeled_share=modeled_share,
                    modeled_value=round(modeled_value, 2),
                )
            )
        else:
            # Seed-only membership (or no holdings at all): produce no
            # equal-weight estimate. The fund contributes nothing to `lines`.
            unmodeled_fund_value += fund_value
            fund_coverage.append(
                FundCoverage(
                    symbol=fund_symbol,
                    market_value=round(fund_value, 2),
                    has_weights=False,
                    modeled_share=0.0,
                    modeled_value=0.0,
                )
            )

    fund_coverage.sort(key=lambda fc: (-fc.market_value, fc.symbol))

    lines: list[ConcentrationLine] = []
    for symbol in set(direct) | set(lookthrough):
        direct_value = direct.get(symbol, 0.0)
        lookthrough_value = lookthrough.get(symbol, 0.0)
        exposure = direct_value + lookthrough_value
        lines.append(
            ConcentrationLine(
                symbol=symbol,
                exposure_value=round(exposure, 2),
                exposure_percent=round(exposure / total_value * 100, 2),
                direct_value=round(direct_value, 2),
                lookthrough_value=round(lookthrough_value, 2),
                source_funds=sorted(sources.get(symbol, set())),
            )
        )
    lines.sort(key=lambda line: (-line.exposure_percent, line.symbol))

    modeled_value = sum(direct.values()) + sum(lookthrough.values())

    return ConcentrationReport(
        lines=lines[:limit],
        total_value=round(total_value, 2),
        modeled_value=round(modeled_value, 2),
        unmodeled_fund_value=round(unmodeled_fund_value, 2),
        cash_value=round(cash_value, 2),
        other_value=round(other_value, 2),
        fund_coverage=fund_coverage,
    )
