from __future__ import annotations

import sqlite3
from dataclasses import dataclass

TOP_TEN_LIMIT = 10

# THE top-ten rule, expressed once.
#
# `etf_holding` mixes two kinds of row: seed select-list rows (membership only,
# `weight IS NULL`, at most ten per fund) and imported holdings-file rows (real
# weights, possibly hundreds per fund). Every consumer whose output is *defined*
# as a top ten must see ten names, not every row a fund happens to have.
#
# The rule: prefer a fund's ten highest-weight `holdings_file` rows; fall back
# to its `seed_top_ten` membership rows when it has no imported weights. The
# first ORDER BY key partitions the two sources, so imported rows always take
# the ten slots when any exist and the remaining keys only ever compare rows of
# the same source: weight descending for imported rows, stored rank for seed
# rows (whose weights are all NULL and therefore tie). `holding_symbol` breaks
# any remaining tie so the result is deterministic.
#
# This is a CTE fragment, not a complete statement: prepend it to a query that
# selects from `atlas_top_ten`. Per-fund callers should use `top_ten_holdings`;
# only universe-wide aggregates need the CTE directly.
TOP_TEN_CTE = f"""
WITH atlas_top_ten AS (
    SELECT etf_symbol, holding_symbol, weight, source, top_rank
    FROM (
        SELECT
            etf_symbol,
            holding_symbol,
            weight,
            source,
            ROW_NUMBER() OVER (
                PARTITION BY etf_symbol
                ORDER BY
                    CASE WHEN source = 'holdings_file' THEN 0 ELSE 1 END,
                    COALESCE(weight, 0) DESC,
                    rank,
                    holding_symbol
            ) AS top_rank
        FROM etf_holding
    )
    WHERE top_rank <= {TOP_TEN_LIMIT}
)
"""


HOLDINGS_BASIS_LABELS = {
    "holdings_file": "imported holdings file",
    "seed_top_ten": "seed select-list",
}


def holdings_basis_label(source: str | None) -> str:
    """Describe a top ten's source in words the investor reads.

    ``None`` means the fund has no holdings rows at all. An unrecognized
    source is reported by name rather than folded into "no holdings":
    ``etf_holding.source`` carries no CHECK constraint, so a future source
    type or a hand-edited row would otherwise be labelled as having no
    holdings while plainly having some.
    """
    if source is None:
        return "no holdings"
    return HOLDINGS_BASIS_LABELS.get(source, f"unrecognized source '{source}'")


@dataclass(frozen=True)
class OverlapResult:
    left_symbol: str
    right_symbol: str
    shared_count: int
    left_count: int
    right_count: int
    jaccard_percent: float
    shared_symbols: list[str]
    left_source: str | None
    right_source: str | None

    @property
    def mixed_basis(self) -> bool:
        """True when the two sides' top tens come from different kinds of source.

        An issuer's real top ten and a seed select-list top ten are both valid
        top tens, but they are not the same kind of list, so an overlap figure
        across them is not like-for-like. A side with no holdings at all is not
        a mismatch — there is no second basis to disagree with.
        """
        if self.left_source is None or self.right_source is None:
            return False
        return self.left_source != self.right_source


def top_ten_holdings(conn: sqlite3.Connection, etf_symbol: str) -> list[str]:
    """Return a fund's top ten holding symbols, best available source.

    Prefers the ten highest-weight rows from an imported holdings file; falls
    back to the seed select-list top-ten membership when no weights exist.
    Returned in top-ten order (heaviest first when weights are known, seed rank
    order otherwise), and never longer than ten entries.
    """
    rows = conn.execute(
        TOP_TEN_CTE + "SELECT holding_symbol FROM atlas_top_ten WHERE etf_symbol = ? ORDER BY top_rank",
        (etf_symbol.upper(),),
    ).fetchall()
    return [row["holding_symbol"] for row in rows]


def holdings_weight_source(conn: sqlite3.Connection, etf_symbol: str) -> str | None:
    """Return the source backing a fund's top ten: 'holdings_file', 'seed_top_ten', or None."""
    row = conn.execute(
        TOP_TEN_CTE + "SELECT source FROM atlas_top_ten WHERE etf_symbol = ? ORDER BY top_rank LIMIT 1",
        (etf_symbol.upper(),),
    ).fetchone()
    return row["source"] if row else None


def compare_etfs(conn: sqlite3.Connection, left_symbol: str, right_symbol: str) -> OverlapResult:
    """Compare top-ten holdings for two ETFs.

    Each side is the fund's real top ten by weight where a holdings file has
    been imported, and its seed select-list top ten otherwise (see
    :func:`top_ten_holdings`). The comparison is membership-only: it counts
    shared names and ignores how much of each fund they represent. Weighted
    overlap math is still future work.

    Each side's basis is reported in ``left_source`` / ``right_source``, and
    ``mixed_basis`` flags a comparison drawn across the two kinds, so the
    caller can say which list it actually compared rather than implying the
    two are alike.
    """
    left = set(top_ten_holdings(conn, left_symbol))
    right = set(top_ten_holdings(conn, right_symbol))
    shared = sorted(left & right)
    union_count = len(left | right)
    jaccard = (len(shared) / union_count * 100.0) if union_count else 0.0
    return OverlapResult(
        left_symbol=left_symbol.upper(),
        right_symbol=right_symbol.upper(),
        shared_count=len(shared),
        left_count=len(left),
        right_count=len(right),
        jaccard_percent=round(jaccard, 1),
        shared_symbols=shared,
        left_source=holdings_weight_source(conn, left_symbol),
        right_source=holdings_weight_source(conn, right_symbol),
    )


def top_repeated_holdings(conn: sqlite3.Connection, limit: int = 20) -> list[sqlite3.Row]:
    """Return companies that appear most often in ETF top-ten holdings.

    Counts each fund's top ten only (:data:`TOP_TEN_CTE`), so importing a
    300-row holdings file for a fund does not inflate that fund's contribution
    thirtyfold.
    """
    return conn.execute(
        TOP_TEN_CTE
        + """
        SELECT holding_symbol, COUNT(*) AS etf_count, GROUP_CONCAT(etf_symbol, ', ') AS etfs
        FROM atlas_top_ten
        GROUP BY holding_symbol
        HAVING COUNT(*) > 1
        ORDER BY etf_count DESC, holding_symbol
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
