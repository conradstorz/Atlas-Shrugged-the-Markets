from fastapi.testclient import TestClient

from atlas.web.app import app


def test_dashboard_loads() -> None:
    client = TestClient(app)
    response = client.get("/")
    assert response.status_code == 200
    assert "Atlas" in response.text
    assert "Maps, not predictions" in response.text


def test_etf_scores_page_loads() -> None:
    client = TestClient(app)
    response = client.get("/etfs?limit=5")
    assert response.status_code == 200
    assert "ETF Scores" in response.text
