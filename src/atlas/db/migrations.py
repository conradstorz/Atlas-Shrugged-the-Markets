"""Versioned, in-place schema migrations, run once per database by `connect()`.

`PRAGMA user_version` records which migrations a database has been through.
`connect()` first runs `schema.sql` (all `CREATE TABLE IF NOT EXISTS`, so a
legacy database gains the new empty tables alongside its old ones), then calls
:func:`migrate`, which runs every step above the stored version, in order,
each in its own transaction. A fresh database has nothing to migrate and is
stamped `LATEST_VERSION` immediately.

Steps never lose investor data: `portfolio`, `portfolio_position` and
`decision_journal_entry` are not referenced by any step, holdings rows are
copied with row-count guards, and any failure rolls the step back and leaves
`user_version` untouched, so the database stays usable by the previous binary.
"""
from __future__ import annotations

import sqlite3

from atlas.exceptions import AtlasError

LATEST_VERSION = 1


def migrate(conn: sqlite3.Connection) -> None:
    version = conn.execute("PRAGMA user_version").fetchone()[0]
    if version >= LATEST_VERSION:
        return
    if version == 0 and not _table_exists(conn, "etf"):
        # Fresh database: schema.sql just created the current tables and
        # there is no prototype data to normalize. Stamp and return.
        conn.execute(f"PRAGMA user_version = {LATEST_VERSION}")
        conn.commit()
        return
    for target, step in STEPS:
        if version < target:
            _run_step(conn, target, step)
            version = target


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return (
        conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = ?", (name,)
        ).fetchone()
        is not None
    )


def _count(conn: sqlite3.Connection, table: str) -> int:
    return int(conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0])


def _run_step(conn: sqlite3.Connection, target: int, step) -> None:
    conn.commit()  # Leave any implicit transaction before touching PRAGMAs.
    foreign_keys_were_on = bool(conn.execute("PRAGMA foreign_keys").fetchone()[0])
    # A PRAGMA is a no-op inside a transaction, so this must precede BEGIN.
    conn.execute("PRAGMA foreign_keys = OFF")
    try:
        conn.execute("BEGIN")
        try:
            step(conn)
            # user_version lives in the database header and is transactional:
            # a rollback reverts the stamp along with the step's changes.
            conn.execute(f"PRAGMA user_version = {target}")
            conn.commit()
        except BaseException as exc:
            conn.rollback()
            if isinstance(exc, AtlasError):
                raise
            raise AtlasError(
                f"Migration to schema version {target} failed and was rolled back; "
                f"your data is unchanged: {exc}"
                # "Your data", not "the database": the empty current-schema
                # tables that connect()'s bootstrap created before this step
                # remain, which is harmless — every row and the old tables
                # are exactly as they were, and the next open retries cleanly.
            ) from exc
    finally:
        if foreign_keys_were_on:
            conn.execute("PRAGMA foreign_keys = ON")


def _normalize_universe(conn: sqlite3.Connection) -> None:
    """v0.8: etf/etf_holding/etf_score -> asset/fund/company/fund_holding/fund_score.

    Copies by column name into the new tables, then drops the old ones. Handles
    every legacy shape in one pass: a narrow-key `etf_holding` copies cleanly
    because the wide key is a superset, and a NOT-NULL-era `etf_score` copies
    cleanly because the new columns are nullable. Pre-existing orphan holdings
    (an `etf_holding` row whose fund has no `etf` row) become stub funds rather
    than being dropped — they are the investor's data.
    """
    holding_count = _count(conn, "etf_holding") if _table_exists(conn, "etf_holding") else 0
    score_count = _count(conn, "etf_score") if _table_exists(conn, "etf_score") else 0

    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) "
        "SELECT symbol, description, 'fund' FROM etf"
    )
    conn.execute(
        """
        INSERT INTO fund (
            symbol, description, fund_type, category, select_list,
            gross_expense_ratio, information_technology_exposure, source
        )
        SELECT symbol, description, fund_type, category, select_list,
               gross_expense_ratio, information_technology_exposure, source
        FROM etf
        """
    )
    if _table_exists(conn, "etf_holding"):
        # Orphan fund symbols first (rows referencing a missing etf), so they
        # win the 'fund' type over the company-stub insert below.
        conn.execute(
            "INSERT INTO asset (symbol, name, asset_type) "
            "SELECT DISTINCT etf_symbol, '', 'fund' FROM etf_holding "
            "WHERE etf_symbol NOT IN (SELECT symbol FROM asset)"
        )
        conn.execute(
            "INSERT INTO fund (symbol, description) "
            "SELECT DISTINCT etf_symbol, '' FROM etf_holding "
            "WHERE etf_symbol NOT IN (SELECT symbol FROM fund)"
        )
        conn.execute(
            "INSERT INTO asset (symbol, name, asset_type) "
            "SELECT holding_symbol, MAX(holding_name), 'company' FROM etf_holding "
            "WHERE holding_symbol NOT IN (SELECT symbol FROM asset) "
            "GROUP BY holding_symbol"
        )
        conn.execute(
            "INSERT INTO company (symbol) "
            "SELECT symbol FROM asset WHERE asset_type = 'company'"
        )
        conn.execute(
            """
            INSERT INTO fund_holding (
                fund_symbol, holding_symbol, holding_name, rank, weight, source
            )
            SELECT etf_symbol, holding_symbol, holding_name, rank, weight, source
            FROM etf_holding
            """
        )
    if _table_exists(conn, "etf_score"):
        conn.execute(
            """
            INSERT INTO fund_score (
                symbol, role, overall_score, ai_score, resilience_score,
                cost_score, diversification_score, explanation
            )
            SELECT symbol, role, overall_score, ai_score, resilience_score,
                   cost_score, diversification_score, explanation
            FROM etf_score
            """
        )

    copied_holdings = _count(conn, "fund_holding")
    if copied_holdings != holding_count:
        raise AtlasError(
            "Refusing to normalize: fund_holding holds "
            f"{copied_holdings} rows, not the {holding_count} etf_holding had. "
            "Nothing was changed."
        )
    copied_scores = _count(conn, "fund_score")
    if copied_scores != score_count:
        raise AtlasError(
            "Refusing to normalize: fund_score holds "
            f"{copied_scores} rows, not the {score_count} etf_score had. "
            "Nothing was changed."
        )
    for table in ("asset", "fund", "company", "fund_holding", "fund_score"):
        orphans = conn.execute(f"PRAGMA foreign_key_check({table})").fetchall()
        if orphans:
            raise AtlasError(
                f"Refusing to normalize: {len(orphans)} {table} row(s) would "
                "reference a missing row. Nothing was changed."
            )

    if _table_exists(conn, "etf_holding"):
        conn.execute("DROP TABLE etf_holding")
    if _table_exists(conn, "etf_score"):
        conn.execute("DROP TABLE etf_score")
    conn.execute("DROP TABLE etf")


STEPS: tuple[tuple[int, object], ...] = ((1, _normalize_universe),)
