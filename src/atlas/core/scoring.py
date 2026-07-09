from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScoreComponent:
    """One explainable component of a larger score."""

    name: str
    score: float
    weight: float
    explanation: str
    estimated: bool = True


@dataclass(frozen=True)
class ExplainableScore:
    """A score that can be explained and audited."""

    subject: str
    model_name: str
    components: list[ScoreComponent] = field(default_factory=list)
    explanation: str = ""

    @property
    def overall_score(self) -> float:
        """Return the weighted total score on a 0-100 scale."""
        if not self.components:
            return 0.0
        total_weight = sum(component.weight for component in self.components)
        if total_weight == 0:
            return 0.0
        weighted = sum(component.score * component.weight for component in self.components)
        return round(weighted / total_weight, 2)
