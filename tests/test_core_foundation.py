from atlas.core.scoring import ExplainableScore, ScoreComponent
from atlas.core.themes import AI_THEME_TREE


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
