from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas.providers.holdings_file import HoldingsFileProvider
from atlas.providers.portfolio_files import PortfolioCsvProvider
from atlas.providers.seed_universe import SeedUniverseProvider

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open an Atlas SQLite database and ensure the schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _repair_etf_score_schema(conn)
    return conn


def _repair_etf_score_schema(conn: sqlite3.Connection) -> None:
    """Rebuild `etf_score` if it predates nullable diversification scores.

    `diversification_score` is NULL when a fund's breadth could not be
    measured. `CREATE TABLE IF NOT EXISTS` cannot relax the old NOT NULL
    constraint on a database created before that change, so an existing local
    database would reject those rows.

    `etf_score` is a pure cache of derived values, recomputed from `etf` and
    `etf_holding` by `score_all`, so dropping it loses nothing. Never do this
    to a table holding data the investor entered — `portfolio`,
    `portfolio_position` and `decision_journal_entry` are typed in by hand and
    are deliberately untouched here.
    """
    columns = conn.execute("PRAGMA table_info(etf_score)").fetchall()
    if not columns:
        return  # No such table yet; the schema script has just created it.
    legacy = any(
        column["name"] == "diversification_score" and column["notnull"] for column in columns
    )
    if not legacy:
        return
    conn.execute("DROP TABLE etf_score")
    # Re-run the schema script: every other table already exists, so this
    # recreates exactly the one table that was just dropped.
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def load_seed_universe(conn: sqlite3.Connection, seed_path: Path) -> int:
    """Load the seed ETF universe CSV and parse top-ten holdings."""
    count = 0
    for fund in SeedUniverseProvider(seed_path).iter_funds():
        symbol = fund["symbol"]
        conn.execute(
            """
            INSERT INTO etf (
                symbol, description, fund_type, category, select_list,
                top_ten_holdings, gross_expense_ratio,
                information_technology_exposure, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                description=excluded.description,
                fund_type=excluded.fund_type,
                category=excluded.category,
                select_list=excluded.select_list,
                top_ten_holdings=excluded.top_ten_holdings,
                gross_expense_ratio=excluded.gross_expense_ratio,
                information_technology_exposure=excluded.information_technology_exposure,
                source=excluded.source
            """,
            (
                symbol,
                fund["description"],
                fund["fund_type"],
                fund["category"],
                fund["select_list"],
                fund["top_ten_holdings"],
                fund["gross_expense_ratio"],
                fund["information_technology_exposure"],
                fund["source"],
            ),
        )
        # Real imported holdings (source='holdings_file') always outrank the
        # seed top-ten list. Without this check, the DELETE+INSERT below —
        # which runs on every `generate-report` and `atlas serve` startup —
        # would silently flip an imported row back to seed_top_ten (with a
        # now-stale weight attached), destroying real data. If the fund has
        # any holdings_file rows, skip touching its holdings entirely; the
        # only way to replace imported holdings is to re-import them.
        has_holdings_file_rows = (
            conn.execute(
                "SELECT 1 FROM etf_holding WHERE etf_symbol = ? AND source = 'holdings_file' LIMIT 1",
                (symbol,),
            ).fetchone()
            is not None
        )
        if not has_holdings_file_rows:
            conn.execute("DELETE FROM etf_holding WHERE etf_symbol = ? AND source = 'seed_top_ten'", (symbol,))
            for rank, holding_symbol in enumerate(fund["holding_symbols"], start=1):
                conn.execute(
                    """
                    INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source)
                    VALUES (?, ?, ?, 'seed_top_ten')
                    ON CONFLICT(etf_symbol, holding_symbol) DO UPDATE SET
                        rank=excluded.rank,
                        source=excluded.source
                    """,
                    (symbol, holding_symbol, rank),
                )
        count += 1
    conn.commit()
    return count


def load_portfolio_csv(conn: sqlite3.Connection, portfolio_name: str, portfolio_path: Path) -> int:
    """Import a private portfolio CSV with Symbol and Market Value columns.

    Accepted market-value column names: Market Value, Value, Amount.
    Existing positions for the same portfolio are replaced.
    """
    conn.execute(
        "INSERT INTO portfolio (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
        (portfolio_name,),
    )
    portfolio_id = conn.execute("SELECT id FROM portfolio WHERE name = ?", (portfolio_name,)).fetchone()["id"]
    conn.execute("DELETE FROM portfolio_position WHERE portfolio_id = ?", (portfolio_id,))

    count = 0
    for position in PortfolioCsvProvider().import_file(portfolio_path):
        conn.execute(
            """
            INSERT INTO portfolio_position (
                portfolio_id, symbol, description, asset_type, market_value, notes
            ) VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                portfolio_id,
                position["symbol"],
                position["description"],
                position["asset_type"],
                position["market_value"],
                position["notes"],
            ),
        )
        count += 1
    conn.commit()
    return count


def load_fund_holdings(conn: sqlite3.Connection, etf_symbol: str, path: Path) -> int:
    """Import an issuer holdings-with-weights CSV, replacing prior holdings for the fund.

    Parses ``path`` with :class:`~atlas.providers.holdings_file.HoldingsFileProvider`,
    deletes all existing ``etf_holding`` rows for the fund (both sources), then
    inserts the parsed rows tagged ``source='holdings_file'`` with ``rank``
    assigned 1..N by descending weight. Re-import fully replaces rather than
    accumulating. Imported holdings always outrank the seed top-ten list (see
    ``load_seed_universe``).

    Inserts a minimal ``etf`` row for the symbol (description ``''``) if one
    does not already exist, since ``etf_holding`` has a foreign key to
    ``etf(symbol)`` and holdings may be imported for a fund outside the seed
    universe. Returns the number of holdings stored.
    """
    symbol = etf_symbol.strip().upper()
    holdings = sorted(HoldingsFileProvider(path).iter_holdings(), key=lambda h: h.weight, reverse=True)

    conn.execute(
        "INSERT INTO etf (symbol, description) VALUES (?, ?) ON CONFLICT(symbol) DO NOTHING",
        (symbol, ""),
    )
    conn.execute("DELETE FROM etf_holding WHERE etf_symbol = ?", (symbol,))
    for rank, holding in enumerate(holdings, start=1):
        conn.execute(
            """
            INSERT INTO etf_holding (
                etf_symbol, holding_symbol, holding_name, rank, weight, source
            ) VALUES (?, ?, ?, ?, ?, 'holdings_file')
            """,
            (symbol, holding.holding_symbol, holding.holding_name, rank, holding.weight),
        )
    conn.commit()
    return len(holdings)
