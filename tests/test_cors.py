from fastapi.testclient import TestClient

from app.core.config import Settings


def test_cors_origin_list_parsing():
    raw = " http://a.com/ , http://b.com,, "
    s = Settings(_env_file=None, database_url="sqlite://", cors_origins=raw)
    assert s.cors_origin_list == ["http://a.com", "http://b.com"]
    assert Settings(_env_file=None, database_url="sqlite://").cors_origin_list == []


def test_main_app_enables_cors_only_for_configured_origins(monkeypatch):
    import importlib

    import app.main as main
    from app.core.config import settings

    monkeypatch.setattr(settings, "cors_origins", "http://localhost:5000")
    reloaded = importlib.reload(main)
    try:
        client = TestClient(reloaded.app)
        ok = client.options(
            "/auth/login",
            headers={
                "Origin": "http://localhost:5000",
                "Access-Control-Request-Method": "POST",
                "Access-Control-Request-Headers": "authorization,content-type",
            },
        )
        assert ok.headers["access-control-allow-origin"] == "http://localhost:5000"
        bad = client.options(
            "/auth/login",
            headers={"Origin": "http://evil.com", "Access-Control-Request-Method": "POST"},
        )
        assert "access-control-allow-origin" not in bad.headers
    finally:
        monkeypatch.setattr(settings, "cors_origins", "")
        importlib.reload(main)

