import pytest

from atlas.exceptions import AtlasSecretError
from atlas.platform.secrets import EnvironmentSecretProvider, require_secret


def test_secret_value_redacts_string_forms() -> None:
    provider = EnvironmentSecretProvider({"TOKEN": "super-secret"})
    secret = require_secret(provider, "TOKEN")

    assert secret.reveal() == "super-secret"
    assert str(secret) == "***REDACTED***"
    assert "super-secret" not in repr(secret)


def test_required_secret_raises_safe_error() -> None:
    provider = EnvironmentSecretProvider({})

    with pytest.raises(AtlasSecretError) as excinfo:
        require_secret(provider, "MISSING_SECRET")

    assert "MISSING_SECRET" in str(excinfo.value)
