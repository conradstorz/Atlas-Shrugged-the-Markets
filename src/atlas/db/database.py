from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from atlas.db.migrations import migrate
from atlas.exceptions import AtlasDataError
from atlas.providers.holdings_file import HoldingsFileProvider
from atlas.providers.portfolio_files import PortfolioCsvProvider
from atlas.providers.seed_universe import SeedUniverseProvider

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open an Atlas SQLite database, ensure the schema exists, run migrations."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    migrate(conn)
    return conn


def _ensure_holding_asset(
    conn: sqlite3.Connection, holding_symbol: str, holding_name: str | None
) -> None:
    """Ensure a held symbol exists in `asset`, as a company unless already a fund.

    `fund_holding.holding_symbol` references `asset(symbol)`: a fund's holding
    may be a company or another fund. An unknown symbol becomes a company stub;
    a symbol already registered (either type) is left exactly as it is.
    """
    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'company') "
        "ON CONFLICT(symbol) DO NOTHING",
        (holding_symbol, holding_name),
    )
    conn.execute(
        "INSERT OR IGNORE INTO company (symbol) "
        "SELECT symbol FROM asset WHERE symbol = ? AND asset_type = 'company'",
        (holding_symbol,),
    )


def load_seed_universe(conn: sqlite3.Connection, seed_path: Path) -> int:
    """Load the seed ETF universe CSV and parse top-ten holdings."""
    count = 0
    for fund in SeedUniverseProvider(seed_path).iter_funds():
        symbol = fund["symbol"]
        conn.execute(
            """
            INSERT INTO asset (symbol, name, asset_type) VALUES (?, ?, 'fund')
            ON CONFLICT(symbol) DO UPDATE SET name=excluded.name, asset_type='fund'
            """,
            (symbol, fund["description"]),
        )
        # A symbol previously known only as some fund's holding was a company
        # stub; the seed CSV saying it is a fund is better evidence. Promote:
        # the company row goes, existing fund_holding rows that reference the
        # symbol keep working because their FK targets asset, not company.
        conn.execute("DELETE FROM company WHERE symbol = ?", (symbol,))
        conn.execute(
            """
            INSERT INTO fund (
                symbol, description, fund_type, category, select_list,
                gross_expense_ratio, information_technology_exposure, source
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(symbol) DO UPDATE SET
                description=excluded.description,
                fund_type=excluded.fund_type,
                category=excluded.category,
                select_list=excluded.select_list,
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
            "DELETE FROM fund_holding WHERE fund_symbol = ? AND source = 'seed_top_ten'",
            (symbol,),
        )
        for rank, holding_symbol in enumerate(fund["holding_symbols"], start=1):
            # The conflict target must name every column of the primary key,
            # which is (fund_symbol, holding_symbol, source). Naming only the
            # first two is not a silent mistake — SQLite rejects a target that
            # matches no unique constraint — but naming them and getting the
            # *effect* wrong would be: this statement runs on every
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
            # not by this clause, which is the point of the wide key.
            _ensure_holding_asset(conn, holding_symbol, None)
            conn.execute(
                """
                INSERT INTO fund_holding (fund_symbol, holding_symbol, rank, source)
                VALUES (?, ?, ?, 'seed_top_ten')
                ON CONFLICT(fund_symbol, holding_symbol, source) DO UPDATE SET
                    rank=excluded.rank
                WHERE fund_holding.source <> 'holdings_file'
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


def load_fund_holdings(conn: sqlite3.Connection, fund_symbol: str, path: Path) -> int:
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
    the rows that mattered. ``fund_holding``'s key includes ``source``, so both
    rows now exist for such a symbol. Which of the two sources a fund's top ten
    is drawn from is decided at read time by
    :data:`~atlas.analytics.overlap.TOP_TEN_CTE`, not by destroying rows here.

    Inserts a minimal ``asset``/``fund`` row pair for the symbol (description
    ``''``) if one does not already exist, since ``fund_holding.fund_symbol``
    has a foreign key to ``fund(symbol)`` and holdings may be imported for a
    fund outside the seed universe. Each held symbol likewise gets an ``asset``
    row (a company stub unless already known) for the
    ``fund_holding.holding_symbol`` foreign key. Returns the number of holdings
    stored.
    """
    symbol = fund_symbol.strip().upper()
    holdings = sorted(HoldingsFileProvider(path).iter_holdings(), key=lambda h: h.weight, reverse=True)

    existing = conn.execute(
        "SELECT asset_type FROM asset WHERE symbol = ?", (symbol,)
    ).fetchone()
    if existing is not None and existing["asset_type"] == "company":
        raise AtlasDataError(
            f"{symbol} is registered as a company (a holding of other funds), "
            "not a fund. Not importing a holdings file for it."
        )

    conn.execute(
        "INSERT INTO asset (symbol, name, asset_type) VALUES (?, '', 'fund') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )
    conn.execute(
        "INSERT INTO fund (symbol, description) VALUES (?, '') "
        "ON CONFLICT(symbol) DO NOTHING",
        (symbol,),
    )
    conn.execute(
        "DELETE FROM fund_holding WHERE fund_symbol = ? AND source = 'holdings_file'",
        (symbol,),
    )
    for rank, holding in enumerate(holdings, start=1):
        # No delete of the fund's other-source rows for this symbol. The key is
        # PRIMARY KEY (fund_symbol, holding_symbol, source), so a name held in
        # both the seed top ten and the imported file is stored twice, once per
        # kind of evidence, and neither displaces the other. The `DELETE` above
        # already cleared this fund's previous import, which is the only set an
        # import is entitled to replace.
        _ensure_holding_asset(conn, holding.holding_symbol, holding.holding_name)
        conn.execute(
            """
            INSERT INTO fund_holding (
                fund_symbol, holding_symbol, holding_name, rank, weight, source
            ) VALUES (?, ?, ?, ?, ?, 'holdings_file')
            """,
            (symbol, holding.holding_symbol, holding.holding_name, rank, holding.weight),
        )
    conn.commit()
    return len(holdings)


@dataclass(frozen=True)
class ForgetFundResult:
    """What `forget_fund` removed for one symbol, and what it deliberately left.

    ``holdings_removed`` counts `fund_holding` rows across both sources
    (`seed_top_ten` and `holdings_file`). ``portfolio_positions`` is the number
    of `portfolio_position` rows still referencing the symbol after the fund
    was forgotten — those are the investor's actual holdings, not derived from
    the universe, and `forget_fund` never touches them; a nonzero count here is
    how the caller learns the position survives.
    """

    symbol: str
    holdings_removed: int
    score_removed: bool
    portfolio_positions: int


def forget_fund(conn: sqlite3.Connection, symbol: str) -> ForgetFundResult:
    """Remove a fund and everything Atlas derived from it: undo `load_fund_holdings`.

    `load_fund_holdings` deliberately creates a minimal `fund` row for a symbol
    outside the seed universe, so holdings can be imported for a fund the seed
    select-list does not name. That is wanted, but it means a typo'd symbol
    creates a permanent phantom fund with no way to remove it. `forget_fund` is
    the undo: it deletes the symbol's `fund_holding` rows (both sources), its
    `fund_score` row, its `fund` row, and its `asset` row.

    Deletes `fund_holding` before `fund` because `fund_holding.fund_symbol`
    references `fund(symbol)` and `connect()` sets `PRAGMA foreign_keys = ON`;
    deleting `fund` first would violate that constraint. The `asset` row goes
    last, and only if no surviving `fund_holding` row still names the symbol as
    a holding — that foreign key points at `asset(symbol)`. Immediately before
    the `asset` delete, the symbol's `company` row (if any) is deleted under
    the same condition: a symbol can be dual-registered, holding both a
    `company` row (from being named as a holding) and a `fund` row (from
    having holdings imported for it), and `company.symbol` also references
    `asset(symbol)`.

    Never touches `portfolio_position`. Those rows are the investor's actual
    holdings, typed in or imported from a broker export, and Atlas cannot
    rebuild a single one of them — they are not derived from the universe at
    all, unlike `fund_holding` and `fund_score`, which `forget_fund` treats as
    fully re-importable or recomputable. The returned
    :class:`ForgetFundResult` reports how many positions still reference the
    symbol so the caller can tell the investor the position remains.

    Raises :class:`~atlas.exceptions.AtlasDataError` if `symbol` has no `fund`
    row, rather than pretending to succeed on a symbol with nothing to forget.
    """
    symbol = symbol.strip().upper()
    exists = conn.execute("SELECT 1 FROM fund WHERE symbol = ?", (symbol,)).fetchone()
    if exists is None:
        raise AtlasDataError(f"{symbol} is not in the universe. Nothing to forget.")

    holdings_removed = conn.execute(
        "DELETE FROM fund_holding WHERE fund_symbol = ?", (symbol,)
    ).rowcount
    score_removed = (
        conn.execute("DELETE FROM fund_score WHERE symbol = ?", (symbol,)).rowcount > 0
    )
    conn.execute("DELETE FROM fund WHERE symbol = ?", (symbol,))
    # A symbol can be dual-registered today: a company stub (created because
    # some fund's holdings named it) that later had holdings imported for it,
    # gaining a fund row too, with asset_type left at 'company' throughout.
    # company.symbol references asset(symbol), so the asset delete below
    # would fail while this child row survives; it must go first whenever the
    # asset row is also going away. Same condition as the asset delete: when
    # the asset row survives (another fund still holds the symbol), it keeps
    # asset_type='company', and the company row must stay as its subtype row.
    conn.execute(
        "DELETE FROM company WHERE symbol = ? "
        "AND NOT EXISTS (SELECT 1 FROM fund_holding WHERE holding_symbol = ?)",
        (symbol, symbol),
    )
    # The fund's own asset row goes too — unless another fund still holds this
    # symbol, in which case the FK from fund_holding.holding_symbol needs it.
    conn.execute(
        "DELETE FROM asset WHERE symbol = ? "
        "AND NOT EXISTS (SELECT 1 FROM fund_holding WHERE holding_symbol = ?)",
        (symbol, symbol),
    )
    # Company stubs exist only as anchors for fund_holding rows or fund rows.
    # Any stub nothing references any more -- neither a fund_holding row nor
    # a fund row of its own -- is residue of the import being undone; sweep
    # it. The fund exclusion matters even here: a symbol elsewhere in the DB
    # can be dual-registered (asset_type='company' plus its own fund row)
    # with no fund_holding row naming it, and that fund row's FK to asset(symbol)
    # would otherwise make the sweep below crash.
    conn.execute(
        "DELETE FROM company WHERE symbol NOT IN (SELECT holding_symbol FROM fund_holding) "
        "AND symbol NOT IN (SELECT symbol FROM fund)"
    )
    conn.execute(
        "DELETE FROM asset WHERE asset_type = 'company' "
        "AND symbol NOT IN (SELECT symbol FROM company) "
        "AND symbol NOT IN (SELECT holding_symbol FROM fund_holding) "
        "AND symbol NOT IN (SELECT symbol FROM fund)"
    )
    # An asset can also be left with NO subtype row at all: forgetting a fund
    # that was itself held by another fund (this function's own asset delete
    # above, three statements up, spares it while a fund_holding row still
    # names it) leaves an asset_type='fund' row with no `fund` row of its own.
    # If that surviving fund_holding reference is later removed too -- e.g. the
    # fund holding it is forgotten next -- neither sweep above catches it: they
    # only look at asset_type='company' rows. Sweep any asset row that is
    # anchored by nothing at all: no company row, no fund row, and no
    # fund_holding reference, regardless of its asset_type.
    conn.execute(
        "DELETE FROM asset WHERE symbol NOT IN (SELECT symbol FROM company) "
        "AND symbol NOT IN (SELECT symbol FROM fund) "
        "AND symbol NOT IN (SELECT holding_symbol FROM fund_holding)"
    )
    portfolio_positions = int(
        conn.execute(
            "SELECT COUNT(*) AS c FROM portfolio_position WHERE symbol = ?", (symbol,)
        ).fetchone()["c"]
    )
    conn.commit()
    return ForgetFundResult(
        symbol=symbol,
        holdings_removed=holdings_removed,
        score_removed=score_removed,
        portfolio_positions=portfolio_positions,
    )
