from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from atlas.exceptions import AtlasConfigurationError


@dataclass(frozen=True)
class AtlasConfig:
    """Immutable runtime configuration for the Atlas Kernel.

    The Kernel owns platform configuration only. Investment-specific settings
    belong to later engines or plugins.
    """

    app_name: str = "Atlas"
    environment: str = "local"
    data_dir: Path = Path(".atlas")
    log_level: str = "INFO"
    host: str = "127.0.0.1"
    port: int = 8000
    plugin_paths: tuple[Path, ...] = ()

    @property
    def database_path(self) -> Path:
        return self.data_dir / "atlas.db"

    def validate(self) -> None:
        if not self.app_name.strip():
            raise AtlasConfigurationError("app_name must not be blank")
        if self.environment not in {"local", "test", "production"}:
            raise AtlasConfigurationError("environment must be one of: local, test, production")
        if self.port < 1 or self.port > 65535:
            raise AtlasConfigurationError("port must be between 1 and 65535")
        if self.log_level.upper() not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
            raise AtlasConfigurationError("log_level is invalid")


def load_config(env: Mapping[str, str] | None = None) -> AtlasConfig:
    """Load immutable Atlas platform configuration from environment variables."""

    source = os.environ if env is None else env

    plugin_paths_raw = source.get("ATLAS_PLUGIN_PATHS", "").strip()
    plugin_paths = tuple(Path(item.strip()) for item in plugin_paths_raw.split(os.pathsep) if item.strip())

    config = AtlasConfig(
        app_name=source.get("ATLAS_APP_NAME", "Atlas"),
        environment=source.get("ATLAS_ENV", "local"),
        data_dir=Path(source.get("ATLAS_DATA_DIR", ".atlas")),
        log_level=source.get("ATLAS_LOG_LEVEL", "INFO"),
        host=source.get("ATLAS_HOST", "127.0.0.1"),
        port=int(source.get("ATLAS_PORT", "8000")),
        plugin_paths=plugin_paths,
    )
    config.validate()
    return config
