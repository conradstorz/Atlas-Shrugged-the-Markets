from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum


class EvidenceKind(str, Enum):
    """Kinds of evidence Atlas may use."""

    FACT = "fact"
    MODEL_OUTPUT = "model_output"
    INVESTOR_BELIEF = "investor_belief"
    OBSERVATION = "observation"


@dataclass(frozen=True)
class Evidence:
    """A fact, model output, belief, or observation used by Atlas."""

    kind: EvidenceKind
    summary: str
    source: str
    confidence: float | None = None
    collected_at: datetime = datetime.now(timezone.utc)
