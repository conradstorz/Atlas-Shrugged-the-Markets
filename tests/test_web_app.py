from pathlib import Path

from fastapi.testclient import TestClient

import atlas.web.app as webapp
from atlas.db.database import connect, load_fund_holdings, load_seed_universe
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


def test_fund_page_top_ten_shows_ten_rows_not_the_whole_holdings_file(tmp_path: Path) -> None:
    """The "Parsed Top-Ten Holdings" heading must mean ten, even after a 30-row import.

    The weights sum to 93%, so the file covers the whole fund and supersedes
    SCHB's seed select-list top ten. A partial file would not: the fund would
    keep showing its seed ten, which the top-ten rule now treats as the better
    list. See ``atlas.analytics.overlap.TOP_TEN_CTE``.
    """
    holdings_csv = tmp_path / "schb.csv"
    holdings_csv.write_text(
        "Ticker,Name,Weight\n"
        + "".join(f"H{index:02d},Holding {index} Inc,{(31 - index) / 5}\n" for index in range(1, 31)),
        encoding="utf-8",
    )
    conn = connect(webapp.DEFAULT_DB)
    load_seed_universe(conn, Path("data/atlas_seed_universe.csv"))
    load_fund_holdings(conn, "SCHB", holdings_csv)
    conn.close()

    response = TestClient(app).get("/etfs/SCHB")

    assert response.status_code == 200
    assert response.text.count("<li>") == 10
    assert "H01</li>" in response.text  # heaviest holding
    assert "H11</li>" not in response.text  # eleventh by weight, correctly dropped
    assert "imported holdings file" in response.text
