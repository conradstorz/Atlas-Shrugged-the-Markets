import pytest

from atlas.exceptions import AtlasPluginError
from atlas.platform.plugins import PluginHost, PluginManifest
from atlas.plugins.hello import HelloAtlasPlugin


def test_plugin_lifecycle_initializes_and_shutdowns() -> None:
    plugin = HelloAtlasPlugin()
    host = PluginHost()

    host.register(plugin)
    host.initialize()
    assert host.initialized is True
    assert plugin.initialized is True

    host.shutdown()
    assert host.initialized is False
    assert plugin.stopped is True


def test_duplicate_plugin_names_are_rejected() -> None:
    host = PluginHost()
    host.register(HelloAtlasPlugin())

    with pytest.raises(AtlasPluginError):
        host.register(HelloAtlasPlugin())


def test_manifest_requires_name() -> None:
    with pytest.raises(AtlasPluginError):
        PluginManifest(name="", version="1").validate()
