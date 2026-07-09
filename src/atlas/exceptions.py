from __future__ import annotations


class AtlasError(Exception):
    """Base exception for Atlas application failures."""


class AtlasConfigurationError(AtlasError):
    """Raised when Atlas configuration is invalid."""


class AtlasSecretError(AtlasError):
    """Raised when required secrets are missing or invalid."""


class AtlasPluginError(AtlasError):
    """Raised when a plugin cannot be validated or initialized."""
