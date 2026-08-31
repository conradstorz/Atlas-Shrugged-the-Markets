"""Shared test isolation.

Both the Kernel (via ``ATLAS_DATA_DIR``) and the FastAPI app (via
``atlas.web.app.DEFAULT_DB``) default to the investor's real local data
directory, ``.atlas/``. Without isolation, a plain ``uv run pytest`` loads the
seed universe into and re-scores ``.atlas/atlas.db`` — the live private
database. Every test gets a throwaway data directory instead.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import atlas.web.app as webapp


@pytest.fixture(autouse=True)
def isolate_atlas_data_dir(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Point the Kernel and the web app at a per-test data directory."""
    data_dir = tmp_path / "atlas-data"
    monkeypatch.setenv("ATLAS_DATA_DIR", str(data_dir))
    monkeypatch.setattr(webapp, "DEFAULT_DB", data_dir / "atlas.db")
    # The web app memoizes seed loading and scoring in a module-level global.
    # Reset it so each test starts against its own empty database rather than
    # inheriting whatever a previously-run test initialized.
    monkeypatch.setattr(webapp, "_initialized", False)
