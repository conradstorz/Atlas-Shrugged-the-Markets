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
        # Refresh only this fund's seed rows. An imported holdings file lives
        # alongside them and is never rewritten from here: a fund's seed
        # membership and its real weights are two different pieces of
        # evidence, and only one of them can be reconstructed from the CSV.
        conn.execute(
            "DELETE FROM etf_holding WHERE etf_symbol = ? AND source = 'seed_top_ten'",
            (symbol,),
        )
        for rank, holding_symbol in enumerate(fund["holding_symbols"], start=1):
            # THE GUARD. `etf_holding` allows one row per (fund, symbol), so a
            # seed symbol already occupied by an imported row lands here as a
            # conflict. Without `WHERE etf_holding.source <> 'holdings_file'`
            # this upsert would relabel that row seed_top_ten and overwrite its
            # weight-order rank — on every `generate-report` and every web-app
            # startup, silently converting real issuer data into membership
            # data. The imported row keeps the slot instead; the seed symbol is
            # simply not re-created as a separate row.
            conn.execute(
                """
                INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source)
                VALUES (?, ?, ?, 'seed_top_ten')
                ON CONFLICT(etf_symbol, holding_symbol) DO UPDATE SET
                    rank=excluded.rank,
                    source=excluded.source
                WHERE etf_holding.source <> 'holdings_file'
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
    """Import an issuer holdings-with-weights CSV, replacing prior imports for the fund.

    Parses ``path`` with :class:`~atlas.providers.holdings_file.HoldingsFileProvider`,
    deletes the fund's existing ``holdings_file`` rows — and only those — then
    inserts the parsed rows tagged ``source='holdings_file'`` with ``rank``
    assigned 1..N by descending weight. Re-import fully replaces the imported
    set rather than accumulating.

    Seed select-list rows (``source='seed_top_ten'``) survive an import. They
    are a different kind of evidence: membership in the fund's published top
    ten, which a partial issuer export cannot replace. Deleting them used to
    leave a fund whose "top ten" was however many rows the file happened to
    contain, permanently. Which of the two sources a fund's top ten is drawn
    from is decided at read time by :data:`~atlas.analytics.overlap.TOP_TEN_CTE`,
    not by destroying rows here.

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
    conn.execute(
        "DELETE FROM etf_holding WHERE etf_symbol = ? AND source = 'holdings_file'",
        (symbol,),
    )
    for rank, holding in enumerate(holdings, start=1):
        # `etf_holding` is PRIMARY KEY (etf_symbol, holding_symbol), so the two
        # sources cannot both hold a row for the same symbol. A name in both the
        # seed top ten and the imported file is resolved in favour of the
        # imported row: it carries the real weight that look-through
        # concentration and the top-ten-by-weight rule are computed from, while
        # the seed row carries membership and nothing else. The colliding seed
        # row is deleted here, in the open, rather than being converted by an
        # ON CONFLICT clause whose effect is easy to miss.
        conn.execute(
            "DELETE FROM etf_holding WHERE etf_symbol = ? AND holding_symbol = ?",
            (symbol, holding.holding_symbol),
        )
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
