import asyncio
from datetime import UTC, datetime, timedelta

from app.jobs.sync_fixtures import sync_fixtures
from app.models import Match, MatchStatus
from app.providers.base import ProviderError
from app.providers.dto import FixtureDTO
from app.providers.fake import FakeProvider

NOW = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)


def fake():
    return FakeProvider(now=lambda: NOW, anchor=NOW.replace(hour=0))


def run(db, provider, codes=None):
    return asyncio.run(sync_fixtures(db, provider, codes))


class StubProvider:
    def __init__(self, fixtures=None, failing=()):
        self.fixtures = fixtures or {}
        self.failing = set(failing)

    async def get_fixtures(self, code):
        if code in self.failing:
            raise ProviderError("boom")
        return self.fixtures.get(code, [])

    async def get_match_result(self, external_id):
        raise NotImplementedError


def dto(ext="x1", code="PL", home="A", away="B", hours=10, status=MatchStatus.SCHEDULED):
    return FixtureDTO(
        external_id=ext,
        competition_code=code,
        home_team=home,
        away_team=away,
        kickoff_at=NOW + timedelta(hours=hours),
        status=status,
    )


def test_creates_all_fixtures(db):
    report = run(db, fake())
    assert report.created == 12 and report.updated == 0
    assert db.query(Match).count() == 12


def test_is_idempotent(db):
    run(db, fake())
    report = run(db, fake())
    assert report.created == 0 and report.updated == 0
    assert db.query(Match).count() == 12


def test_updates_changed_kickoff_and_teams(db):
    run(db, StubProvider({"PL": [dto()]}), ["PL"])
    changed = dto(home="Nuevo", hours=20)
    report = run(db, StubProvider({"PL": [changed]}), ["PL"])
    assert report.updated == 1 and report.created == 0
    match = db.query(Match).one()
    assert match.home_team == "Nuevo"
    assert match.kickoff_at.replace(tzinfo=UTC) == NOW + timedelta(hours=20)


def test_status_follows_provider_until_finished(db):
    run(db, StubProvider({"PL": [dto()]}), ["PL"])
    run(db, StubProvider({"PL": [dto(status=MatchStatus.LIVE)]}), ["PL"])
    assert db.query(Match).one().status == MatchStatus.LIVE


def test_does_not_overwrite_finished_match(db):
    run(db, StubProvider({"PL": [dto()]}), ["PL"])
    match = db.query(Match).one()
    match.status, match.home_score, match.away_score = MatchStatus.FINISHED, 2, 1
    db.commit()
    run(db, StubProvider({"PL": [dto(status=MatchStatus.SCHEDULED)]}), ["PL"])
    match = db.query(Match).one()
    assert (match.status, match.home_score, match.away_score) == (MatchStatus.FINISHED, 2, 1)


def test_unknown_competition_is_skipped(db):
    report = run(db, fake(), ["NOPE"])
    assert report.skipped == 1 and report.created == 0


def test_provider_failure_does_not_stop_other_competitions(db):
    provider = StubProvider({"UCL": [dto("u1", "UCL")], "PL": [dto("p1", "PL")]}, failing=["PL"])
    report = run(db, provider, ["PL", "UCL"])
    assert report.skipped == 1 and report.created == 1
    assert [m.external_id for m in db.query(Match)] == ["u1"]


def test_match_is_linked_to_its_competition(db):
    run(db, StubProvider({"UCL": [dto("u1", "UCL")]}), ["UCL"])
    assert db.query(Match).one().competition.code == "UCL"
