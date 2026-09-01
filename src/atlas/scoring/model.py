from __future__ import annotations

from dataclasses import dataclass

# The scoring heuristic's own version, stated in one place. The CLI, the web
# dashboard, and the Markdown report all label scores with it; when they each
# carried their own literal they drifted (v0.4 vs v0.5) and told the investor
# two different things about the same numbers. Bump this when the heuristic in
# `atlas.scoring.engine` actually changes.
SCORER_VERSION = "v0.4"


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
