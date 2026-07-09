from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Mapping, Protocol

from atlas.exceptions import AtlasSecretError


@dataclass(frozen=True)
class SecretValue:
    """A redacted secret wrapper.

    Secret values should never be printed directly. Use reveal() only at the
    boundary where the secret is required by an external provider.
    """

    name: str
    _value: str

    def reveal(self) -> str:
        return self._value

    def __str__(self) -> str:  # pragma: no cover - defensive safety
        return "***REDACTED***"

    def __repr__(self) -> str:  # pragma: no cover - defensive safety
        return f"SecretValue(name={self.name!r}, value='***REDACTED***')"


class SecretProvider(Protocol):
    """Protocol implemented by all Atlas secret providers."""

    def get_secret(self, name: str) -> SecretValue | None:
        """Return a secret value or None when it does not exist."""


class EnvironmentSecretProvider:
    """Secret provider backed by environment variables."""

    def __init__(self, env: Mapping[str, str] | None = None) -> None:
        self._env = os.environ if env is None else env

    def get_secret(self, name: str) -> SecretValue | None:
        value = self._env.get(name)
        if value is None:
            return None
        return SecretValue(name=name, _value=value)


def require_secret(provider: SecretProvider, name: str) -> SecretValue:
    """Return a required secret or raise a safe, non-leaking error."""

    secret = provider.get_secret(name)
    if secret is None or not secret.reveal():
        raise AtlasSecretError(f"Required secret is missing: {name}")
    return secret
