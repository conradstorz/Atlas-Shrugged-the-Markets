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
# ten by weight where an issuer holdings file has been imported. Bump this when
# the heuristic in `atlas.scoring.engine` actually changes.
SCORER_VERSION = "v0.8"


@dataclass(frozen=True)
class ScoreBreakdown:
    symbol: str
    role: str
    overall_score: int
    ai_score: int
    resilience_score: int
    cost_score: int
    diversification_score: int
    explanation: str
