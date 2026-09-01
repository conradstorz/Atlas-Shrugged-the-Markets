from __future__ import annotations

from dataclasses import dataclass

# The scoring heuristic's own version, stated in one place. The CLI, the web
# dashboard, and the Markdown report all label scores with it; when they each
# carried their own literal they drifted (v0.4 vs v0.5) and told the investor
# two different things about the same numbers.
#
# Neither drifted literal was true. The scorer stopped being the v0.4 heuristic
# when cost and resilience were grounded in real expense-ratio and IT-exposure
# data, and diversification began being measured from holdings overlap; its
# basis changed again in v0.8, when that measurement moved to a fund's real top
# ten by weight where an issuer holdings file has been imported. v0.9 replaced
# that overlap metric — which measured crowding, not diversification — with
# measured holdings breadth, and excludes the component entirely (rather than
# defaulting it) for funds whose breadth cannot be measured. v0.10 extended
# that same rule to cost and resilience — no expense ratio means no cost score,
# no information-technology exposure means no resilience score — and made a
# fund whose only surviving component is the AI keyword heuristic unscored
# outright. Bump this when the heuristic in `atlas.scoring.engine` actually
# changes.
SCORER_VERSION = "v0.10"


@dataclass(frozen=True)
class ScoreBreakdown:
    """One fund's score, with every component either measured or absent.

    A ``None`` component means Atlas had no data to measure it from, so it was
    excluded from ``overall_score`` rather than filled in with a stand-in
    value. ``0`` is never a sentinel: it is a real, bad score.
    """

    symbol: str
    # `role` and `ai_score` are keyword heuristics over the fund's description
    # and category, so they are always available and never None. They are worth
    # showing even for a fund that has no overall score.
    role: str
    # None means no data-grounded component could be measured at all — only the
    # AI keyword heuristic survived — so no overall score was produced. See
    # `atlas.scoring.engine.score_etf`.
    overall_score: int | None
    ai_score: int
    # None means the fund has no parsable information-technology exposure, so
    # the role-based resilience default could not be eroded by real data and
    # was excluded rather than reported un-eroded.
    resilience_score: int | None
    # None means the fund has no parsable gross expense ratio, so cost was
    # excluded rather than given a mid-scale stand-in.
    cost_score: int | None
    # None means the fund's breadth was not measured, so diversification was
    # excluded from `overall_score` rather than guessed at. 0 is a real score
    # meaning "extremely concentrated" and is never used as a stand-in.
    diversification_score: int | None
    explanation: str


def format_component(value: int | None) -> str:
    """Render a score or component for display, as an em dash when unmeasured.

    Shared by the CLI table, the Markdown report and the web dashboard so all
    three say the same thing about a number Atlas did not measure. It applies
    to ``overall_score`` as well as to the individual components: an unscored
    fund shows a dash in the Score column rather than a misleading figure.
    """
    return "—" if value is None else str(value)


def score_sort_key(value: int | None) -> tuple[bool, int]:
    """Sort key ranking funds by score descending, with unscored funds last.

    ``None`` cannot be compared with ``int``, so every ranking of scores has to
    say explicitly where an unscored fund goes. It goes at the bottom: Atlas
    has no basis for placing it anywhere else. Used with a stable sort and no
    ``reverse``, so funds sharing a score keep their incoming (symbol) order.
    """
    return (value is None, -value if value is not None else 0)
