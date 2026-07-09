"""The web app should load the seed and score the universe once, not per request."""

from pathlib import Path

from fastapi.testclient import TestClient

import atlas.web.app as webapp


def _fresh_client(monkeypatch, tmp_path: Path) -> TestClient:
    monkeypatch.setattr(webapp, "DEFAULT_DB", tmp_path / "atlas.db")
    monkeypatch.setattr(webapp, "DEFAULT_SEED", Path("data/atlas_seed_universe.csv"))
    monkeypatch.setattr(webapp, "_initialized", False)
    return TestClient(webapp.app)


def test_scoring_runs_at_most_once_across_requests(monkeypatch, tmp_path: Path) -> None:
    calls = {"n": 0}
    real_score_all = webapp.score_all

    def counting_score_all(conn):
        calls["n"] += 1
        return real_score_all(conn)

    monkeypatch.setattr(webapp, "score_all", counting_score_all)
    client = _fresh_client(monkeypatch, tmp_path)

    client.get("/")
    client.get("/etfs")
    client.get("/")

    assert calls["n"] <= 1


def test_seed_is_loaded_at_most_once_across_requests(monkeypatch, tmp_path: Path) -> None:
    calls = {"n": 0}
    real_load = webapp.load_seed_universe

    def counting_load(conn, seed):
        calls["n"] += 1
        return real_load(conn, seed)

    monkeypatch.setattr(webapp, "load_seed_universe", counting_load)
    client = _fresh_client(monkeypatch, tmp_path)

    client.get("/")
    client.get("/etfs")
    client.get("/")

    assert calls["n"] <= 1


def test_dashboard_still_shows_scored_etfs(monkeypatch, tmp_path: Path) -> None:
    client = _fresh_client(monkeypatch, tmp_path)

    response = client.get("/etfs?limit=200")

    assert response.status_code == 200
    assert "ETF Scores" in response.text
    # A real seed symbol should be rendered somewhere in the ranked universe,
    # proving persisted scores were served (rank is not assumed).
    assert "SCHB" in response.text
