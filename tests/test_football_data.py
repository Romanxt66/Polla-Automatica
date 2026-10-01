import asyncio
from datetime import UTC, datetime

import httpx
import pytest

from app.models.match import MatchStatus
from app.providers.base import ProviderError, UnsupportedCompetition
from app.providers.football_data import FootballDataProvider, map_status


def match_item(mid=1, status="TIMED", full=(None, None), regular=None, date="2026-10-03T15:00:00Z"):
    score = {"fullTime": {"home": full[0], "away": full[1]}}
    if regular is not None:
        score["regularTime"] = {"home": regular[0], "away": regular[1]}
    return {
        "id": mid,
        "utcDate": date,
        "status": status,
        "homeTeam": {"name": "Arsenal FC"},
        "awayTeam": {"name": "Chelsea FC"},
        "score": score,
    }


def make(handler, **kwargs):
    client = httpx.AsyncClient(base_url="https://test", transport=httpx.MockTransport(handler))
    return FootballDataProvider(token="t", client=client, **kwargs)


def ok(matches, headers=None):
    return httpx.Response(200, json={"matches": matches}, headers=headers)


def run(coro):
    return asyncio.run(coro)


@pytest.mark.parametrize(
    "status,expected",
    [
        ("SCHEDULED", MatchStatus.SCHEDULED),
        ("TIMED", MatchStatus.SCHEDULED),
        ("IN_PLAY", MatchStatus.LIVE),
        ("PAUSED", MatchStatus.LIVE),
        ("FINISHED", MatchStatus.FINISHED),
        ("AWARDED", MatchStatus.FINISHED),
        ("POSTPONED", MatchStatus.POSTPONED),
        ("SUSPENDED", MatchStatus.POSTPONED),
        ("CANCELLED", MatchStatus.POSTPONED),
        ("???", MatchStatus.SCHEDULED),
    ],
)
def test_status_mapping(status, expected):
    assert map_status(status) == expected


def test_requires_token():
    with pytest.raises(ProviderError):
        FootballDataProvider(token="")


def test_fixtures_map_competition_codes_and_fields():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.url.path, dict(request.url.params)))
        return ok([match_item(1), match_item(2, "FINISHED", (2, 1))])

    p = make(handler)
    pl = run(p.get_fixtures("PL"))
    ucl = run(p.get_fixtures("UCL"))
    assert [s[0] for s in seen] == ["/competitions/PL/matches", "/competitions/CL/matches"]
    assert seen[0][1] == {}  # sin season = temporada en curso
    assert [f.external_id for f in pl] == ["1", "2"]
    assert pl[0].home_team == "Arsenal FC" and pl[0].competition_code == "PL"
    assert ucl[0].competition_code == "UCL"
    assert pl[0].kickoff_at == datetime(2026, 10, 3, 15, 0, tzinfo=UTC)
    assert (pl[0].status, pl[0].home_score) == (MatchStatus.SCHEDULED, None)
    assert (pl[1].status, pl[1].home_score, pl[1].away_score) == (MatchStatus.FINISHED, 2, 1)


def test_season_is_sent_when_configured():
    seen = []

    def handler(request):
        seen.append(dict(request.url.params))
        return ok([])

    run(make(handler, season=2025).get_fixtures("PL"))
    assert seen == [{"season": "2025"}]


def test_betplay_is_unsupported_and_makes_no_request():
    def handler(request):
        raise AssertionError("no debe llamar a la API")

    with pytest.raises(UnsupportedCompetition):
        run(make(handler).get_fixtures("BETPLAY"))


def test_unsupported_is_a_provider_error_subclass():
    assert issubclass(UnsupportedCompetition, ProviderError)


def test_ninety_minute_score_is_used_when_there_was_extra_time_or_penalties():
    item = match_item(5, "FINISHED", full=(5, 4), regular=(1, 1))  # 1-1 y penales
    result = run(make(lambda r: httpx.Response(200, json=item)).get_match_result("5"))
    assert (result.home_score, result.away_score) == (1, 1)


def test_regular_finished_uses_fulltime():
    item = match_item(5, "FINISHED", full=(3, 0))
    result = run(make(lambda r: httpx.Response(200, json=item)).get_match_result("5"))
    assert (result.status, result.home_score, result.away_score) == (MatchStatus.FINISHED, 3, 0)


def test_live_uses_current_score_and_scheduled_has_none():
    live = match_item(5, "IN_PLAY", full=(1, 0))
    r = run(make(lambda _: httpx.Response(200, json=live)).get_match_result("5"))
    assert (r.status, r.home_score, r.away_score) == (MatchStatus.LIVE, 1, 0)
    sched = match_item(6)
    r = run(make(lambda _: httpx.Response(200, json=sched)).get_match_result("6"))
    assert (r.status, r.home_score) == (MatchStatus.SCHEDULED, None)


def test_batch_one_request_with_comma_separated_ids():
    seen = []

    def handler(request: httpx.Request):
        seen.append((request.url.path, dict(request.url.params)))
        return ok([match_item(1, "FINISHED", (2, 1)), match_item(2, "IN_PLAY", (0, 0))])

    results = run(make(handler).get_match_results(["1", "2"]))
    assert seen == [("/matches", {"ids": "1,2"})]
    assert results["1"].status == MatchStatus.FINISHED and results["2"].status == MatchStatus.LIVE


def test_batch_splits_by_twenty_and_empty_makes_no_request():
    sizes = []

    def handler(request: httpx.Request):
        ids = request.url.params["ids"].split(",")
        sizes.append(len(ids))
        return ok([match_item(int(i)) for i in ids])

    p = make(handler)
    assert len(run(p.get_match_results([str(i) for i in range(1, 46)]))) == 45
    assert sizes == [20, 20, 5]
    assert run(make(lambda r: (_ for _ in ()).throw(AssertionError())).get_match_results([])) == {}


def test_batch_falls_back_to_one_by_one_when_filter_is_rejected():
    seen = []

    def handler(request: httpx.Request):
        seen.append(request.url.path)
        if request.url.path == "/matches":
            return httpx.Response(403, json={"message": "no disponible en tu plan"})
        mid = int(request.url.path.split("/")[-1])
        return httpx.Response(200, json=match_item(mid, "FINISHED", (1, 0)))

    results = run(make(handler).get_match_results(["7", "8"]))
    assert seen == ["/matches", "/matches/7", "/matches/8"]
    assert set(results) == {"7", "8"}


def test_rate_limit_and_http_errors_raise_provider_error():
    with pytest.raises(ProviderError, match="límite"):
        run(make(lambda r: httpx.Response(429)).get_match_result("1"))
    with pytest.raises(ProviderError):
        run(make(lambda r: httpx.Response(500)).get_match_result("1"))

    def boom(request):
        raise httpx.ConnectError("sin red")

    with pytest.raises(ProviderError):
        run(make(boom).get_match_result("1"))


def test_factory_builds_football_data(monkeypatch):
    from app.core.config import settings
    from app.providers import get_provider

    monkeypatch.setattr(settings, "results_provider", "football_data")
    monkeypatch.setattr(settings, "football_data_token", "abc")
    assert isinstance(get_provider(), FootballDataProvider)
    monkeypatch.setattr(settings, "football_data_token", "")
    with pytest.raises(ProviderError):
        get_provider()
