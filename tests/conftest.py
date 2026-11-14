import pytest


@pytest.fixture(autouse=True)
def _isolate_non_live_env(request, monkeypatch):
    """Ensure non-live tests never read TYPESAFE_API_KEY and never call paid APIs."""
    if request.node.get_closest_marker("live") is None:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
