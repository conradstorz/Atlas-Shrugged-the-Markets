from pathlib import Path

from atlas.application.kernel import ATLAS_VERSION, AtlasKernel
from atlas.platform.config import AtlasConfig
from atlas.platform.secrets import EnvironmentSecretProvider
from atlas.plugins.hello import HelloAtlasPlugin


def test_kernel_starts_reports_health_and_shutdowns(tmp_path: Path) -> None:
    kernel = AtlasKernel(
        config=AtlasConfig(environment="test", data_dir=tmp_path, log_level="INFO"),
        secret_provider=EnvironmentSecretProvider({}),
    )
    plugin = HelloAtlasPlugin()
    kernel.register_plugin(plugin)

    kernel.start()
    report = kernel.health_service().report(ready=kernel.started)

    assert kernel.started is True
    assert plugin.initialized is True
    assert report.ready is True
    assert report.version == ATLAS_VERSION
    assert report.plugins_loaded == 1

    kernel.shutdown()
    assert kernel.started is False
    assert plugin.stopped is True
