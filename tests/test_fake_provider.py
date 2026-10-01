import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.models.match import MatchStatus
from app.providers import get_provider
from app.providers.base import ProviderError
from app.providers.fake import FakeProvider

NOW = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)


def run(coro):
    return asyncio.run(coro)


ANCHOR = NOW.replace(hour=0)


def provider(now=NOW):
    return FakeProvider(now=lambda: now, anchor=ANCHOR)


@pytest.mark.parametrize("code", ["BETPLAY", "UCL", "PL"])
def test_fixtures_per_competition(code):
    fixtures = run(provider().get_fixtures(code))
    assert len(fixtures) == 4
    assert {f.competition_code for f in fixtures} == {code}
    assert len({f.external_id for f in fixtures}) == 4
    assert all(f.kickoff_at.tzinfo is not None for f in fixtures)


def test_has_both_finished_and_scheduled():
    statuses = {f.status for f in run(provider().get_fixtures("PL"))}
    assert statuses == {MatchStatus.FINISHED, MatchStatus.SCHEDULED}


def test_external_ids_unique_across_competitions():
    ids = [f.external_id for c in ("BETPLAY", "UCL", "PL") for f in run(provider().get_fixtures(c))]
    assert len(ids) == len(set(ids)) == 12


def test_unknown_competition():
    with pytest.raises(ProviderError):
        run(provider().get_fixtures("XXX"))


def test_fixtures_do_not_move_as_time_passes():
    a = run(provider(NOW).get_fixtures("PL"))
    b = run(provider(NOW + timedelta(days=5)).get_fixtures("PL"))
    assert [f.kickoff_at for f in a] == [f.kickoff_at for f in b]
    assert [f.external_id for f in a] == [f.external_id for f in b]


def test_finished_result_has_deterministic_score():
    ext = "fake-PL-0"
    r1 = run(provider().get_match_result(ext))
    r2 = run(provider(NOW + timedelta(hours=1)).get_match_result(ext))
    assert r1.status == MatchStatus.FINISHED
    assert r1.home_score is not None and r1.away_score is not None
    assert (r1.home_score, r1.away_score) == (r2.home_score, r2.away_score)


def test_scheduled_result_has_no_score():
    r = run(provider().get_match_result("fake-PL-2"))
    assert r.status == MatchStatus.SCHEDULED
    assert r.home_score is None and r.away_score is None


def test_match_goes_scheduled_live_finished_over_time():
    kickoff = run(provider().get_fixtures("PL"))[2].kickoff_at
    ext = "fake-PL-2"
    statuses = [
        run(provider(kickoff + delta).get_match_result(ext)).status
        for delta in (timedelta(minutes=-1), timedelta(minutes=30), timedelta(hours=3))
    ]
    assert statuses == [MatchStatus.SCHEDULED, MatchStatus.LIVE, MatchStatus.FINISHED]


def test_unknown_match():
    with pytest.raises(ProviderError):
        run(provider().get_match_result("nope"))


def test_factory_returns_fake_by_default():
    assert isinstance(get_provider(), FakeProvider)


def test_batch_matches_single_results_and_skips_unknown():
    p = provider()
    ids = ["fake-PL-0", "fake-PL-2", "nope"]
    batch = run(p.get_match_results(ids))
    assert set(batch) == {"fake-PL-0", "fake-PL-2"}
    for ext in ("fake-PL-0", "fake-PL-2"):
        assert batch[ext] == run(p.get_match_result(ext))
