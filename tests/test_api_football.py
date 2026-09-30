import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app.models.match import MatchStatus
from app.providers.api_football import ApiFootballProvider, default_season, map_status
from app.providers.base import ProviderError


def fixture_item(fid=100, short="NS", goals=(None, None), fulltime=(None, None)):
    return {
        "fixture": {"id": fid, "date": "2026-10-03T15:00:00-05:00", "status": {"short": short}},
        "teams": {"home": {"name": "Nacional"}, "away": {"name": "Millonarios"}},
        "goals": {"home": goals[0], "away": goals[1]},
        "score": {"fulltime": {"home": fulltime[0], "away": fulltime[1]}},
    }


def make(handler, **kwargs):
    client = httpx.AsyncClient(
        base_url="https://test", transport=httpx.MockTransport(handler)
    )
    return ApiFootballProvider(api_key="k", client=client, **kwargs)


def ok(items, headers=None):
    return httpx.Response(200, json={"errors": [], "response": items}, headers=headers)


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize(
    "short,expected",
    [
        ("NS", MatchStatus.SCHEDULED),
        ("TBD", MatchStatus.SCHEDULED),
        ("1H", MatchStatus.LIVE),
        ("HT", MatchStatus.LIVE),
        ("2H", MatchStatus.LIVE),
        ("ET", MatchStatus.LIVE),
        ("FT", MatchStatus.FINISHED),
        ("AET", MatchStatus.FINISHED),
        ("PEN", MatchStatus.FINISHED),
        ("PST", MatchStatus.POSTPONED),
        ("CANC", MatchStatus.POSTPONED),
        ("???", MatchStatus.SCHEDULED),
    ],
)
def test_status_mapping(short, expected):
    assert map_status(short) == expected


def test_default_season():
    assert default_season("PL", datetime(2026, 10, 1, tzinfo=UTC)) == 2026
    assert default_season("UCL", datetime(2027, 3, 1, tzinfo=UTC)) == 2026
    assert default_season("BETPLAY", datetime(2027, 3, 1, tzinfo=UTC)) == 2027


def test_requires_api_key():
    with pytest.raises(ProviderError):
        ApiFootballProvider(api_key="")


def test_get_fixtures_maps_and_sends_league_and_season():
    seen = {}

    def handler(request: httpx.Request):
        seen["path"] = request.url.path
        seen["params"] = dict(request.url.params)
        return ok([fixture_item(1), fixture_item(2, "FT", (2, 1), (2, 1))])

    fixtures = run(make(handler, season=2026).get_fixtures("BETPLAY"))
    assert seen["path"] == "/fixtures"
    assert seen["params"] == {"league": "239", "season": "2026"}
    assert [f.external_id for f in fixtures] == ["1", "2"]
    assert fixtures[0].home_team == "Nacional" and fixtures[0].competition_code == "BETPLAY"
    assert fixtures[0].kickoff_at == datetime(2026, 10, 3, 20, 0, tzinfo=UTC)  # a UTC
    assert [f.status for f in fixtures] == [MatchStatus.SCHEDULED, MatchStatus.FINISHED]
    assert (fixtures[0].home_score, fixtures[0].away_score) == (None, None)
    assert (fixtures[1].home_score, fixtures[1].away_score) == (2, 1)


def test_league_ids():
    params = []

    def handler(request):
        params.append(request.url.params["league"])
        return ok([])

    p = make(handler, season=2026)
    for code in ("BETPLAY", "UCL", "PL"):
        run(p.get_fixtures(code))
    assert params == ["239", "2", "39"]


def test_unknown_competition():
    with pytest.raises(ProviderError):
        run(make(lambda r: ok([])).get_fixtures("XXX"))


def test_result_finished_uses_ninety_minute_score_not_extra_time():
    item = fixture_item(5, "AET", goals=(3, 2), fulltime=(2, 2))
    result = run(make(lambda r: ok([item])).get_match_result("5"))
    assert result.status == MatchStatus.FINISHED
    assert (result.home_score, result.away_score) == (2, 2)
    assert result.external_id == "5"


def test_result_live_uses_current_goals():
    item = fixture_item(5, "2H", goals=(1, 0))
    result = run(make(lambda r: ok([item])).get_match_result("5"))
    assert (result.status, result.home_score, result.away_score) == (MatchStatus.LIVE, 1, 0)


def test_result_scheduled_has_no_score():
    result = run(make(lambda r: ok([fixture_item(5)])).get_match_result("5"))
    assert result.status == MatchStatus.SCHEDULED
    assert result.home_score is None and result.away_score is None


def test_result_not_found():
    with pytest.raises(ProviderError):
        run(make(lambda r: ok([])).get_match_result("999"))


def test_api_level_errors_raise_even_with_http_200():
    def handler(request):
        return httpx.Response(200, json={"errors": {"requests": "limit reached"}, "response": []})

    with pytest.raises(ProviderError, match="limit reached"):
        run(make(handler).get_match_result("1"))


def test_http_and_network_errors_raise_provider_error():
    with pytest.raises(ProviderError):
        run(make(lambda r: httpx.Response(500)).get_match_result("1"))

    def boom(request):
        raise httpx.ConnectError("sin red")

    with pytest.raises(ProviderError):
        run(make(boom).get_match_result("1"))


def test_invalid_json_raises_provider_error():
    with pytest.raises(ProviderError):
        run(make(lambda r: httpx.Response(200, text="no es json")).get_match_result("1"))


def test_factory_builds_api_football(monkeypatch):
    from app.core.config import settings
    from app.providers import get_provider

    monkeypatch.setattr(settings, "results_provider", "api_football")
    monkeypatch.setattr(settings, "api_football_key", "abc")
    assert isinstance(get_provider(), ApiFootballProvider)
    monkeypatch.setattr(settings, "api_football_key", "")
    with pytest.raises(ProviderError):
        get_provider()
    monkeypatch.setattr(settings, "results_provider", "otro")
    with pytest.raises(ProviderError):
        get_provider()
