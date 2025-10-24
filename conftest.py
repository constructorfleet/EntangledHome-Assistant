"""Global pytest fixtures for adapter service tests."""

import pytest


@pytest.fixture
def enable_custom_integrations():
    """No-op fixture to satisfy pytest.ini configuration when HA plugin is absent."""

    yield
