from __future__ import annotations

from dataclasses import dataclass, field

from atlas.application.health import HealthService
from atlas.platform.config import AtlasConfig, load_config
from atlas.platform.logging import configure_logging, get_logger
from atlas.platform.plugins import AtlasPlugin, PluginHost
from atlas.platform.secrets import EnvironmentSecretProvider, SecretProvider

ATLAS_VERSION = "0.7.0"


@dataclass
class AtlasKernel:
    """Smallest executable Atlas platform.

    The Kernel owns platform lifecycle only. It intentionally has no investment
    knowledge and must remain independent from domain engines.
    """

    config: AtlasConfig
    secret_provider: SecretProvider
    plugin_host: PluginHost = field(default_factory=PluginHost)
    started: bool = False

    @classmethod
    def from_environment(cls) -> "AtlasKernel":
        config = load_config()
        return cls(config=config, secret_provider=EnvironmentSecretProvider())

    def register_plugin(self, plugin: AtlasPlugin) -> None:
        if self.started:
            raise RuntimeError("plugins must be registered before kernel startup")
        self.plugin_host.register(plugin)

    def start(self) -> None:
        self.config.validate()
        self.config.data_dir.mkdir(parents=True, exist_ok=True)
        configure_logging(self.config.log_level)
        logger = get_logger("atlas.kernel")
        logger.info("Atlas Kernel starting")
        self.plugin_host.initialize()
        self.started = True
        logger.info("Atlas Kernel ready")

    def shutdown(self) -> None:
        logger = get_logger("atlas.kernel")
        logger.info("Atlas Kernel shutting down")
        self.plugin_host.shutdown()
        self.started = False
        logger.info("Atlas Kernel stopped")

    def health_service(self) -> HealthService:
        return HealthService(self.config, self.plugin_host, ATLAS_VERSION)
