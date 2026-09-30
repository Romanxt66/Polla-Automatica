import asyncio
from datetime import UTC, datetime, timedelta

import pytest

from app.jobs.settle_matches import settle_finished, settle_matches
from app.models import (
    Competition,
    Group,
    GroupMember,
    Match,
    MatchStatus,
    PointsLedger,
    Prediction,
    User,
)
from app.providers.base import ProviderError
from app.providers.dto import MatchResultDTO

NOW = datetime(2026, 10, 1, 18, 0, tzinfo=UTC)


class StubProvider:
    """Devuelve resultados configurados por external_id y cuenta las llamadas."""

    def __init__(self, results=None, failing=()):
        self.results = results or {}
        self.failing = set(failing)
        self.calls: list[str] = []

    async def get_fixtures(self, code):
        raise NotImplementedError

    async def get_match_result(self, external_id):
        self.calls.append(external_id)
        if external_id in self.failing:
            raise ProviderError("boom")
        return self.results[external_id]


def finished(ext, home, away):
    return MatchResultDTO(
        external_id=ext, status=MatchStatus.FINISHED, home_score=home, away_score=away
    )


def settle(db, provider, window=None):
    kwargs = {"window": window} if window else {}
    return asyncio.run(settle_matches(db, provider, now=NOW, **kwargs))


@pytest.fixture()
def world(db):
    comp = db.query(Competition).filter_by(code="PL").one()
    users = [User(email=f"{n}@x.com", username=n, hashed_password="h") for n in ("ana", "beto")]
    db.add_all(users)
    db.flush()
    group = Group(name="g", owner_id=users[0].id, competition_id=comp.id)
    group.members = [GroupMember(user_id=u.id) for u in users]
    db.add(group)
    db.commit()
    return {"comp": comp, "users": users, "group": group}


def add_match(db, world, ext="m1", minutes_ago=150, status=MatchStatus.SCHEDULED):
    m = Match(
        external_id=ext,
        competition_id=world["comp"].id,
        home_team="A",
        away_team="B",
        kickoff_at=NOW - timedelta(minutes=minutes_ago),
        status=status,
    )
    db.add(m)
    db.commit()
    return m


def predict(db, world, user_idx, match, home, away, group=None):
    p = Prediction(
        user_id=world["users"][user_idx].id,
        group_id=(group or world["group"]).id,
        match_id=match.id,
        home_score=home,
        away_score=away,
    )
    db.add(p)
    db.commit()
    return p


def ledger(db):
    return {
        (e.user_id, e.match_id): (e.points, e.is_exact) for e in db.query(PointsLedger).all()
    }


def test_finished_match_awards_points_once(db, world):
    m = add_match(db, world)
    predict(db, world, 0, m, 2, 1)  # exacto
    predict(db, world, 1, m, 1, 0)  # ganador + misma diferencia
    provider = StubProvider({"m1": finished("m1", 2, 1)})

    report = settle(db, provider)
    assert (report.polled, report.results_updated, report.points_created) == (1, 1, 2)
    uid = {u.username: u.id for u in world["users"]}
    assert ledger(db) == {(uid["ana"], m.id): (5, True), (uid["beto"], m.id): (3, False)}
    db.refresh(m)
    assert (m.status, m.home_score, m.away_score) == (MatchStatus.FINISHED, 2, 1)


def test_is_idempotent(db, world):
    m = add_match(db, world)
    predict(db, world, 0, m, 2, 1)
    provider = StubProvider({"m1": finished("m1", 2, 1)})
    settle(db, provider)
    again = settle(db, provider)
    assert again.points_created == 0 and again.polled == 0
    assert db.query(PointsLedger).count() == 1
    assert settle_finished(db) == 0


def test_same_match_in_two_groups_scores_each(db, world):
    m = add_match(db, world)
    other = Group(name="g2", owner_id=world["users"][0].id, competition_id=world["comp"].id)
    other.members = [GroupMember(user_id=world["users"][0].id)]
    db.add(other)
    db.commit()
    predict(db, world, 0, m, 2, 1)
    predict(db, world, 0, m, 0, 0, group=other)
    settle(db, StubProvider({"m1": finished("m1", 2, 1)}))
    assert sorted(e.points for e in db.query(PointsLedger)) == [0, 5]


def test_no_candidates_means_no_api_calls(db, world):
    add_match(db, world, "future", minutes_ago=-60)  # aún no empieza
    add_match(db, world, "old", minutes_ago=60 * 24)  # fuera de la ventana de 4 h
    add_match(db, world, "done", status=MatchStatus.FINISHED)
    provider = StubProvider()
    report = settle(db, provider)
    assert provider.calls == []
    assert report.polled == 0


def test_window_can_be_widened_for_catch_up(db, world):
    add_match(db, world, "old", minutes_ago=60 * 24)
    provider = StubProvider({"old": finished("old", 1, 0)})
    settle(db, provider, window=timedelta(days=3))
    assert provider.calls == ["old"]


def test_live_match_keeps_polling_without_awarding(db, world):
    m = add_match(db, world)
    predict(db, world, 0, m, 1, 0)
    live = MatchResultDTO(external_id="m1", status=MatchStatus.LIVE, home_score=1, away_score=0)
    report = settle(db, StubProvider({"m1": live}))
    assert report.points_created == 0
    db.refresh(m)
    assert m.status == MatchStatus.LIVE
    # en la siguiente vuelta sigue siendo candidato y al terminar puntúa
    settle(db, StubProvider({"m1": finished("m1", 1, 0)}))
    assert db.query(PointsLedger).one().points == 5


def test_postponed_match_awards_nothing(db, world):
    m = add_match(db, world)
    predict(db, world, 0, m, 1, 0)
    postponed = MatchResultDTO(external_id="m1", status=MatchStatus.POSTPONED)
    settle(db, StubProvider({"m1": postponed}))
    db.refresh(m)
    assert m.status == MatchStatus.POSTPONED
    assert db.query(PointsLedger).count() == 0


def test_finished_without_score_awards_nothing_until_score_arrives(db, world):
    m = add_match(db, world)
    predict(db, world, 0, m, 1, 0)
    no_score = MatchResultDTO(external_id="m1", status=MatchStatus.FINISHED)
    settle(db, StubProvider({"m1": no_score}))
    assert db.query(PointsLedger).count() == 0
    # el partido ya está FINISHED; cuando el marcador se completa, el catch-up lo liquida
    m = db.get(Match, m.id)
    m.home_score, m.away_score = 3, 0
    db.commit()
    assert settle_finished(db) == 1
    assert db.query(PointsLedger).one().points == 1


def test_provider_error_does_not_block_other_matches(db, world):
    bad = add_match(db, world, "bad")
    good = add_match(db, world, "good")
    predict(db, world, 0, good, 2, 1)
    predict(db, world, 1, bad, 2, 1)
    provider = StubProvider({"good": finished("good", 2, 1)}, failing=["bad"])
    report = settle(db, provider)
    assert report.points_created == 1
    assert db.get(Match, bad.id).status == MatchStatus.SCHEDULED  # se reintenta después


def test_prediction_made_later_for_finished_match_is_not_double_counted(db, world):
    m = add_match(db, world)
    predict(db, world, 0, m, 2, 1)
    settle(db, StubProvider({"m1": finished("m1", 2, 1)}))
    predict(db, world, 1, m, 0, 0)  # ya liquidado el partido, pero aún sin ledger
    assert settle_finished(db) == 1
    assert db.query(PointsLedger).count() == 2


def test_leaderboard_reflects_settlement(db, world):
    m = add_match(db, world)
    predict(db, world, 0, m, 0, 0)
    predict(db, world, 1, m, 2, 1)
    settle(db, StubProvider({"m1": finished("m1", 2, 1)}))
    from app.services.leaderboard import get_leaderboard

    rows = get_leaderboard(db, world["group"].id)
    assert [(r.username, r.points, r.rank) for r in rows] == [("beto", 5, 1), ("ana", 0, 2)]
