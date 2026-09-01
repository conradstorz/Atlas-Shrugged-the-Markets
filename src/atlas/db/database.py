from __future__ import annotations

import sqlite3
from pathlib import Path

from atlas.exceptions import AtlasError
from atlas.providers.holdings_file import HoldingsFileProvider
from atlas.providers.portfolio_files import PortfolioCsvProvider
from atlas.providers.seed_universe import SeedUniverseProvider

SCHEMA_PATH = Path(__file__).with_name("schema.sql")

# The columns of `etf_holding`, named explicitly so the migration below copies
# by name rather than by position. `SELECT *` would silently misfile every row
# if the column order ever differed between the old table and the new one.
ETF_HOLDING_COLUMNS = ("etf_symbol", "holding_symbol", "holding_name", "rank", "weight", "source")

# The one primary key shape `_widen_etf_holding_key` knows how to widen, in key
# order. Anything else is left untouched rather than rebuilt on a guess.
LEGACY_ETF_HOLDING_KEY = ("etf_symbol", "holding_symbol")

# The `etf_score` columns that must be nullable on the current schema. NULL in
# any of them means "not measured", which is a fact about the fund's data
# rather than a gap in the row. A database created before a given column was
# relaxed still carries NOT NULL on it — `CREATE TABLE IF NOT EXISTS` cannot
# drop a constraint — and would reject the scores `score_all` now produces, so
# `_repair_etf_score_schema` rebuilds the table when it finds any of them still
# NOT NULL. `diversification_score` was relaxed first; `overall_score`,
# `resilience_score` and `cost_score` followed, so a database created between
# the two changes is caught by the same check.
NULLABLE_ETF_SCORE_COLUMNS = frozenset(
    {"overall_score", "resilience_score", "cost_score", "diversification_score"}
)

# `etf_holding` under the widened key, used only to rebuild an existing table.
# Keep it identical to the definition in `schema.sql`, which is what a fresh
# database is created from; `tests/test_holding_key_migration.py` compares the
# two shapes so the pair cannot drift apart unnoticed.
ETF_HOLDING_REBUILD_DDL = """
CREATE TABLE etf_holding_new (
    etf_symbol TEXT NOT NULL REFERENCES etf(symbol),
    holding_symbol TEXT NOT NULL,
    holding_name TEXT,
    rank INTEGER NOT NULL,
    weight REAL,
    source TEXT NOT NULL DEFAULT 'seed_top_ten',
    PRIMARY KEY (etf_symbol, holding_symbol, source)
)
"""


def connect(db_path: Path) -> sqlite3.Connection:
    """Open an Atlas SQLite database and ensure the schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    _repair_etf_score_schema(conn)
    _widen_etf_holding_key(conn)
    return conn


def _repair_etf_score_schema(conn: sqlite3.Connection) -> None:
    """Rebuild `etf_score` if any score column still predates nullability.

    A score column is NULL when Atlas could not measure it: no gross expense
    ratio (`cost_score`), no information-technology exposure
    (`resilience_score`), no holdings file covering the whole fund
    (`diversification_score`), or none of the three — in which case there is no
    `overall_score` either. `CREATE TABLE IF NOT EXISTS` cannot relax a NOT
    NULL constraint on a database that already exists, so without this repair
    an investor's local database would reject exactly the rows that say "not
    measured".

    The check covers every column in `NULLABLE_ETF_SCORE_COLUMNS` rather than
    only the first one to be relaxed, so a database created after
    `diversification_score` became nullable but before the other three did is
    repaired too.

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
        column["name"] in NULLABLE_ETF_SCORE_COLUMNS and column["notnull"] for column in columns
    )
    if not legacy:
        return
    conn.execute("DROP TABLE etf_score")
    # Re-run the schema script: every other table already exists, so this
    # recreates exactly the one table that was just dropped.
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    conn.commit()


def _widen_etf_holding_key(conn: sqlite3.Connection) -> None:
    """Rebuild `etf_holding` if its primary key predates the `source` column.

    The key was `(etf_symbol, holding_symbol)`, which let a fund store only one
    row per company. A fund's seed select-list membership and its imported
    issuer weights are two different pieces of evidence about the same company,
    and the narrow key forced them to fight over one slot: importing a partial
    export of a fund's largest names destroyed exactly the seed rows that
    defined its top ten. The key is now `(etf_symbol, holding_symbol, source)`.

    `CREATE TABLE IF NOT EXISTS` in `schema.sql` cannot do this, because the
    table already exists on an investor's database, and SQLite has no
    `ALTER TABLE` that changes a primary key. The only way is to rebuild:
    create the new table, copy every row into it, drop the old one, rename.

    **No row is lost.** Unlike `_repair_etf_score_schema` above, which drops a
    cache that `score_all` recomputes, `etf_holding` holds issuer holdings
    files the investor downloaded by hand; Atlas cannot recreate a single one
    of them. So the copy names its columns explicitly rather than using
    `SELECT *`, the row count is asserted to be unchanged before the old table
    is dropped and again after the rename, and the whole rebuild runs in one
    transaction that rolls back — losing nothing — if either check fails.
    `portfolio`, `portfolio_position` and `decision_journal_entry` are not
    referenced here at all.

    Foreign keys are disabled around the rebuild and restored to their prior
    value afterwards, per SQLite's documented table-rebuild procedure: with
    them enabled, `DROP TABLE` performs an implicit `DELETE FROM` that fires
    referential actions, and `ALTER TABLE ... RENAME TO` rewrites references
    to the renamed table elsewhere in the schema. The rebuilt table keeps its
    own `REFERENCES etf(symbol)`, and `PRAGMA foreign_key_check` confirms
    before the commit that the rebuild introduced no new orphan.

    Self-detecting and idempotent: it reads the current key from
    `PRAGMA table_info`, whose `pk` column is a column's 1-based position in
    the primary key and 0 outside it. No version flag is consulted, so a
    database that has already been rebuilt — or was created fresh on the
    current schema — is left untouched.
    """
    columns = conn.execute("PRAGMA table_info(etf_holding)").fetchall()
    if not columns:
        return  # No such table yet; the schema script has just created it.
    # Only the exact legacy key is migrated. This rewrites a table holding
    # issuer files the investor downloaded by hand, so it fires on the one
    # shape it was written for and nothing else: an unfamiliar key may encode a
    # property that rebuilding to our assumed shape would silently discard.
    key = [column["name"] for column in sorted(columns, key=lambda c: c["pk"]) if column["pk"]]
    if key != list(LEGACY_ETF_HOLDING_KEY):
        # Already widened, created fresh on the current schema, or a shape this
        # migration does not recognize. Leave it alone.
        return

    conn.commit()  # Leave any implicit transaction before touching PRAGMAs.
    foreign_keys_were_on = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    # A PRAGMA is a no-op inside a transaction, so this must precede BEGIN.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        try:
            before = conn.execute("SELECT COUNT(*) AS c FROM etf_holding").fetchone()["c"]
            # Counted, not required to be zero: an orphan row that was already
            # in the database is the investor's data too, and refusing to
            # migrate — or worse, dropping it — would be the larger harm. What
            # must not happen is the rebuild *introducing* one.
            orphans_before = len(conn.execute("PRAGMA foreign_key_check(etf_holding)").fetchall())
            conn.execute(ETF_HOLDING_REBUILD_DDL)
            column_list = ", ".join(ETF_HOLDING_COLUMNS)
            conn.execute(
                f"INSERT INTO etf_holding_new ({column_list}) SELECT {column_list} FROM etf_holding"
            )
            copied = conn.execute("SELECT COUNT(*) AS c FROM etf_holding_new").fetchone()["c"]
            if copied != before:
                raise AtlasError(
                    "Refusing to widen etf_holding: the copy holds "
                    f"{copied} rows, not the {before} the table had. Nothing was changed."
                )
            conn.execute("DROP TABLE etf_holding")
            conn.execute("ALTER TABLE etf_holding_new RENAME TO etf_holding")
            after = conn.execute("SELECT COUNT(*) AS c FROM etf_holding").fetchone()["c"]
            if after != before:
                raise AtlasError(
                    "Refusing to widen etf_holding: the rebuilt table holds "
                    f"{after} rows, not the {before} it started with. Nothing was changed."
                )
            orphans_after = len(conn.execute("PRAGMA foreign_key_check(etf_holding)").fetchall())
            if orphans_after != orphans_before:
                raise AtlasError(
                    "Refusing to widen etf_holding: the rebuilt table has "
                    f"{orphans_after} row(s) referencing a missing etf, not the "
                    f"{orphans_before} it started with. Nothing was changed."
                )
            conn.commit()
        except BaseException:
            conn.rollback()
            raise
    finally:
        if foreign_keys_were_on:
            conn.execute("PRAGMA foreign_keys = ON")


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
            # The conflict target must name every column of the primary key,
            # which is now (etf_symbol, holding_symbol, source). Naming only
            # the first two is not a silent mistake — SQLite rejects a target
            # that matches no unique constraint — but naming them and getting
            # the *effect* wrong would be: this statement runs on every
            # `generate-report` and every web-app startup, so an upsert that
            # could reach a holdings_file row would convert real issuer data
            # into membership data on a schedule.
            #
            # It cannot reach one. `source` is in the key and the inserted
            # value is the literal 'seed_top_ten', so the only row this can
            # ever conflict with is another seed row for the same fund and
            # symbol — a fund listed twice in the seed CSV, where the later
            # rank wins. The `WHERE` clause below therefore no longer has work
            # to do; it stays as the local, explicit statement that nothing
            # here rewrites imported holdings. That is enforced by the key now,
            # not by this clause, which is the point of widening it.
            conn.execute(
                """
                INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source)
                VALUES (?, ?, ?, 'seed_top_ten')
                ON CONFLICT(etf_symbol, holding_symbol, source) DO UPDATE SET
                    rank=excluded.rank
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

    Seed select-list rows (``source='seed_top_ten'``) survive an import whole —
    including rows for symbols the imported file also names. They are a
    different kind of evidence: membership in the fund's published top ten,
    which a partial issuer export cannot replace. Deleting them used to leave a
    fund whose "top ten" was however many rows the file happened to contain,
    permanently, and a partial export of a fund's *largest* names took exactly
    the rows that mattered. ``etf_holding``'s key includes ``source``, so both
    rows now exist for such a symbol. Which of the two sources a fund's top ten
    is drawn from is decided at read time by
    :data:`~atlas.analytics.overlap.TOP_TEN_CTE`, not by destroying rows here.

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
        # No delete of the fund's other-source rows for this symbol. The key is
        # PRIMARY KEY (etf_symbol, holding_symbol, source), so a name held in
        # both the seed top ten and the imported file is stored twice, once per
        # kind of evidence, and neither displaces the other. The `DELETE` above
        # already cleared this fund's previous import, which is the only set an
        # import is entitled to replace.
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
