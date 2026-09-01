"""What re-seeding may and may not do to a fund that has imported holdings.

``load_seed_universe`` runs on every ``atlas generate-report`` and on web-app
startup, so it is the routine that gets the most chances to quietly destroy
real data. It refreshes every fund's ``seed_top_ten`` rows — including funds
that also have an imported holdings file — but it must never touch a
``holdings_file`` row, and never relabel one as seed data with a stale weight
still attached.

The two sources now coexist for one fund: the seed rows are the fund's
published top-ten membership and the imported rows are its real weights. See
``atlas.analytics.overlap.TOP_TEN_CTE`` for which of the two a fund's top ten
is actually drawn from.
"""

from __future__ import annotations

from pathlib import Path

from atlas.db.database import connect, load_fund_holdings, load_seed_universe

SEED = Path("data/atlas_seed_universe.csv")
INVESCO = Path("tests/fixtures/holdings_invesco.csv")

# DIVB carries a real ten-symbol seed_top_ten list in the seed universe CSV,
# and shares none of those symbols with the Invesco holdings fixture, so it is
# the clean "both sources, no collisions" case.
DIVB_SEED_TOP_TEN = ["ADP", "IBM", "ACN", "JPM", "PAYX", "JNJ", "HPQ", "XOM", "ABBV", "CTSH"]

# ILCB's seed_top_ten list shares five symbols with the Invesco holdings
# fixture below (NVDA, AAPL, MSFT, AMZN, META). That overlap is what makes
# test_imported_holdings_survive_reseed a direct proof rather than an
# indirect one: those five names are the ones the narrower
# (etf_symbol, holding_symbol) key made the two sources fight over, instead of
# merely adding unrelated seed rows alongside untouched holdings_file rows.
ILCB_SEED_TOP_TEN = ["NVDA", "AAPL", "MSFT", "AMZN", "GOOGL", "AVGO", "GOOG", "META", "TSLA", "MU"]
ILCB_SHARED_WITH_INVESCO = ["NVDA", "AAPL", "MSFT", "AMZN", "META"]
INVESCO_SYMBOLS = ["NVDA", "AAPL", "MSFT", "AMZN", "META", "SH"]


def test_imported_holdings_survive_reseed(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "ILCB", INVESCO)
    load_seed_universe(conn, SEED)  # must not flip holdings_file rows back to seed_top_ten

    imported = conn.execute(
        "SELECT holding_symbol, weight FROM etf_holding "
        "WHERE etf_symbol = 'ILCB' AND source = 'holdings_file' ORDER BY rank"
    ).fetchall()
    assert [row["holding_symbol"] for row in imported] == INVESCO_SYMBOLS
    assert imported[0]["weight"] == 9.50
    assert imported[-1]["weight"] == -1.20

    # NVDA sits in both the imported holdings fixture and ILCB's seed
    # top-ten list, so it is the name whose ON CONFLICT resolution actually
    # matters. Since `source` joined the primary key it carries two rows —
    # one per kind of evidence — and the assertion is that re-seeding wrote
    # the seed one and left the imported one exactly as the import stored it,
    # rather than relabeling it seed_top_ten with a stale (missing) weight.
    nvda_rows = conn.execute(
        "SELECT weight, source FROM etf_holding "
        "WHERE etf_symbol = 'ILCB' AND holding_symbol = 'NVDA' ORDER BY source"
    ).fetchall()
    assert [(row["source"], row["weight"]) for row in nvda_rows] == [
        ("holdings_file", 9.50),
        ("seed_top_ten", None),
    ]


def test_reseed_restores_the_whole_seed_list_alongside_imported_holdings(tmp_path: Path) -> None:
    """Seeding no longer skips a fund merely because it has imported holdings.

    Skipping it was the old defence against relabeling, and it left an
    imported fund with no seed membership at all. Then the fund carried both,
    but a symbol in the import cost the fund that seed row, because the key
    allowed only one row per (fund, symbol). With ``source`` in the key the
    fund gets its whole published top ten back — including the five symbols
    the Invesco fixture also names.
    """
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "ILCB", INVESCO)
    load_seed_universe(conn, SEED)

    seed_rows = conn.execute(
        "SELECT holding_symbol FROM etf_holding "
        "WHERE etf_symbol = 'ILCB' AND source = 'seed_top_ten' ORDER BY rank"
    ).fetchall()
    assert [row["holding_symbol"] for row in seed_rows] == ILCB_SEED_TOP_TEN
    # The five shared names are exactly the ones the old key could not keep.
    assert set(ILCB_SHARED_WITH_INVESCO).issubset({row["holding_symbol"] for row in seed_rows})


def test_reseed_gives_a_non_colliding_fund_its_whole_seed_top_ten(tmp_path: Path) -> None:
    """DIVB's seed list and the imported file share no symbols, so both survive whole."""
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "DIVB", INVESCO)
    load_seed_universe(conn, SEED)

    seed_rows = conn.execute(
        "SELECT holding_symbol FROM etf_holding "
        "WHERE etf_symbol = 'DIVB' AND source = 'seed_top_ten' ORDER BY rank"
    ).fetchall()
    assert [row["holding_symbol"] for row in seed_rows] == DIVB_SEED_TOP_TEN

    imported = conn.execute(
        "SELECT holding_symbol FROM etf_holding "
        "WHERE etf_symbol = 'DIVB' AND source = 'holdings_file' ORDER BY rank"
    ).fetchall()
    assert [row["holding_symbol"] for row in imported] == INVESCO_SYMBOLS


def test_repeated_reseeds_do_not_duplicate_or_erode_rows(tmp_path: Path) -> None:
    """`generate-report` re-seeds every run; the row set must be a fixed point."""
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "ILCB", INVESCO)
    load_seed_universe(conn, SEED)
    first = conn.execute(
        "SELECT holding_symbol, rank, weight, source FROM etf_holding "
        "WHERE etf_symbol = 'ILCB' ORDER BY source, holding_symbol"
    ).fetchall()

    load_seed_universe(conn, SEED)
    load_seed_universe(conn, SEED)
    second = conn.execute(
        "SELECT holding_symbol, rank, weight, source FROM etf_holding "
        "WHERE etf_symbol = 'ILCB' ORDER BY source, holding_symbol"
    ).fetchall()

    assert [tuple(row) for row in second] == [tuple(row) for row in first]


def test_funds_without_imported_holdings_still_get_seed_top_ten(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    # Only DIVB has real imported holdings; every other fund, including BNDW,
    # should still receive its seed_top_ten rows normally.
    load_fund_holdings(conn, "DIVB", INVESCO)
    load_seed_universe(conn, SEED)

    bndw_rows = conn.execute(
        "SELECT holding_symbol, source FROM etf_holding WHERE etf_symbol = 'BNDW' ORDER BY rank"
    ).fetchall()
    assert [r["holding_symbol"] for r in bndw_rows] == ["BND", "BNDX"]
    assert all(r["source"] == "seed_top_ten" for r in bndw_rows)


def test_etf_metadata_row_still_updates_on_reseed(tmp_path: Path) -> None:
    conn = connect(tmp_path / "atlas.db")
    load_fund_holdings(conn, "DIVB", INVESCO)
    # Before reseed, load_fund_holdings only inserted a minimal etf row.
    before = conn.execute("SELECT description FROM etf WHERE symbol = 'DIVB'").fetchone()
    assert before["description"] == ""

    load_seed_universe(conn, SEED)

    after = conn.execute("SELECT description, fund_type FROM etf WHERE symbol = 'DIVB'").fetchone()
    assert after["description"] == "iShares Core Dividend ETF"
    assert after["fund_type"] == "ETF"
