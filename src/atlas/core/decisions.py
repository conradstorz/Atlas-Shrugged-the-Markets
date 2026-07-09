from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date


@dataclass(frozen=True)
class InvestmentThesis:
    """The written reason an asset deserves attention or capital."""

    subject: str
    thesis: str
    confidence: int | None = None
    max_allocation_percent: float | None = None
    change_mind_conditions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class InvestmentDecision:
    """A recorded investment decision."""

    subject: str
    decision: str
    thesis: InvestmentThesis
    decision_date: date
    notes: str | None = None
