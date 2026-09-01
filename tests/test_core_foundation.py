from datetime import datetime, timezone
from unittest.mock import patch

from atlas.core.evidence import Evidence, EvidenceKind
from atlas.core.scoring import ExplainableScore, ScoreComponent
from atlas.core.themes import AI_THEME_TREE


def test_evidence_collected_at_is_evaluated_per_instance() -> None:
    """collected_at must use default_factory, not a value fixed at import time.

    A plain `= datetime.now(timezone.utc)` default is evaluated once, when the
    dataclass is defined, so every Evidence would share the same timestamp
    regardless of when it was actually constructed. Mocking `datetime.now` to
    return two distinct values on successive calls proves each instance's
    default is computed at construction time.
    """
    first_time = datetime(2024, 1, 1, 0, 0, 0, tzinfo=timezone.utc)
    second_time = datetime(2024, 1, 1, 0, 0, 1, tzinfo=timezone.utc)

    with patch("atlas.core.evidence.datetime") as mock_datetime:
        mock_datetime.now.side_effect = [first_time, second_time]
        first = Evidence(kind=EvidenceKind.FACT, summary="first", source="test")
        second = Evidence(kind=EvidenceKind.FACT, summary="second", source="test")

    assert first.collected_at == first_time
    assert second.collected_at == second_time
    assert first.collected_at != second.collected_at


def test_explainable_score_weighted_average() -> None:
    score = ExplainableScore(
        subject="SCHB",
        model_name="test",
        components=[
            ScoreComponent("AI", 80, 2, "Broad AI participation."),
            ScoreComponent("Resilience", 90, 1, "Broad diversification."),
        ],
    )
    assert score.overall_score == 83.33


def test_ai_theme_tree_contains_power_grid() -> None:
    names = {theme.name for theme in AI_THEME_TREE}
    assert "AI Power Grid" in names
