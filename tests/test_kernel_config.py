from pathlib import Path

import pytest

from atlas.exceptions import AtlasConfigurationError
from atlas.platform.config import AtlasConfig, load_config


def test_load_config_from_environment_mapping(tmp_path: Path) -> None:
    config = load_config(
        {
            "ATLAS_ENV": "test",
            "ATLAS_DATA_DIR": str(tmp_path),
            "ATLAS_LOG_LEVEL": "DEBUG",
            "ATLAS_PORT": "8123",
        }
    )

    assert config.environment == "test"
    assert config.data_dir == tmp_path
    assert config.log_level == "DEBUG"
    assert config.port == 8123
    assert config.database_path == tmp_path / "atlas.db"


def test_invalid_environment_is_rejected() -> None:
    with pytest.raises(AtlasConfigurationError):
        AtlasConfig(environment="wild-west").validate()
