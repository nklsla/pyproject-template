import pytest


@pytest.fixture
def mock_fix() -> list[str]:
    """Fixture"""
    return ["mocked"]
