from __future__ import annotations

from dataclasses import dataclass

from atlas.platform.config import AtlasConfig
from atlas.platform.plugins import PluginHost


@dataclass(frozen=True)
class HealthReport:
    status: str
    ready: bool
    version: str
    environment: str
    plugins_loaded: int


class HealthService:
    """Read-only health reporting for the Atlas Kernel."""

    def __init__(self, config: AtlasConfig, plugin_host: PluginHost, version: str) -> None:
        self._config = config
        self._plugin_host = plugin_host
        self._version = version

    def report(self, ready: bool) -> HealthReport:
        return HealthReport(
            status="ok" if ready else "starting",
            ready=ready,
            version=self._version,
            environment=self._config.environment,
            plugins_loaded=len(self._plugin_host.plugins),
        )
