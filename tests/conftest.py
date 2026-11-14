import pytest


@pytest.fixture(autouse=True)
def _isolate_non_live_env(request, monkeypatch):
    """Ensure non-live tests never read TYPESAFE_API_KEY and live tests require explicit `-m live`."""
    is_live = request.node.get_closest_marker("live") is not None
    if is_live:
        mark_expr = request.config.getoption("-m") or ""
        if "live" not in mark_expr or "not live" in mark_expr:
            pytest.skip("Live tests only run when explicitly selected with -m live")
    else:
        monkeypatch.delenv("TYPESAFE_API_KEY", raising=False)
