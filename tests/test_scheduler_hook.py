import sys
import types

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


def fake_scheduler(calls: list[str]) -> types.ModuleType:
    module = types.ModuleType("app.jobs.scheduler")
    module.start_scheduler = lambda: calls.append("start")
    module.stop_scheduler = lambda: calls.append("stop")
    return module


def test_disabled_by_default_does_not_touch_scheduler(monkeypatch):
    calls: list[str] = []
    monkeypatch.setitem(sys.modules, "app.jobs.scheduler", fake_scheduler(calls))
    assert settings.scheduler_enabled is False
    with TestClient(app) as c:
        assert c.get("/health").status_code == 200
    assert calls == []


def test_enabled_starts_and_stops_with_app(monkeypatch):
    calls: list[str] = []
    monkeypatch.setitem(sys.modules, "app.jobs.scheduler", fake_scheduler(calls))
    monkeypatch.setattr(settings, "scheduler_enabled", True)
    with TestClient(app) as c:
        assert calls == ["start"]
        assert c.get("/health").status_code == 200
    assert calls == ["start", "stop"]
