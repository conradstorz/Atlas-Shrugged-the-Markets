from __future__ import annotations

from dataclasses import dataclass


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
