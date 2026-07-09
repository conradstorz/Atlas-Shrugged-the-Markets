from __future__ import annotations

from atlas.platform.plugins import PluginManifest


class HelloAtlasPlugin:
    """Minimal example plugin used by ABS-001 acceptance tests."""

    manifest = PluginManifest(
        name="hello-atlas",
        version="0.1.0",
        description="Demonstrates the Atlas Kernel plugin lifecycle.",
    )

    def __init__(self) -> None:
        self.initialized = False
        self.stopped = False

    def initialize(self) -> None:
        self.initialized = True

    def shutdown(self) -> None:
        self.stopped = True
