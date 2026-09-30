from datetime import UTC, datetime, timedelta

import pytest

from app.models import Competition, Match, MatchStatus, Prediction
from tests.test_groups import create, signup
from tests.test_invites import make_invite


def add_match(db, code="PL", hours=24, status=MatchStatus.SCHEDULED, home="Arsenal"):
    comp = db.query(Competition).filter_by(code=code).one()
    m = Match(
        external_id=f"ext-{home}-{code}-{hours}",
        competition_id=comp.id,
        home_team=home,
        away_team="Rival",
        kickoff_at=datetime.now(UTC) + timedelta(hours=hours),
        status=status,
    )
    db.add(m)
    db.commit()
    return m.id


@pytest.fixture()
def ctx(client, db):
    ana = signup(client, "ana")
    gid = create(client, ana, code="PL").json()["id"]
    return {"h": ana, "gid": gid, "mid": add_match(db)}


def put(client, h, gid, mid, home=2, away=1):
    return client.put(
        f"/groups/{gid}/predictions/{mid}", json={"home_score": home, "away_score": away}, headers=h
    )


def test_requires_auth(client, ctx):
    assert client.get(f"/groups/{ctx['gid']}/predictions").status_code == 401
    url = f"/groups/{ctx['gid']}/predictions/{ctx['mid']}"
    r = client.put(url, json={"home_score": 1, "away_score": 0})
    assert r.status_code == 401


def test_create_prediction(client, ctx):
    r = put(client, ctx["h"], ctx["gid"], ctx["mid"], 2, 1)
    assert r.status_code == 200
    body = r.json()
    assert (body["home_score"], body["away_score"]) == (2, 1)
    assert body["match_id"] == ctx["mid"]
    assert body["home_team"] == "Arsenal"


def test_edit_updates_same_row(client, ctx, db):
    put(client, ctx["h"], ctx["gid"], ctx["mid"], 2, 1)
    r = put(client, ctx["h"], ctx["gid"], ctx["mid"], 0, 0)
    assert r.status_code == 200
    assert (r.json()["home_score"], r.json()["away_score"]) == (0, 0)
    assert db.query(Prediction).count() == 1


def test_locked_after_kickoff(client, ctx, db):
    past = add_match(db, hours=-1, home="Pasado")
    r = put(client, ctx["h"], ctx["gid"], past)
    assert r.status_code == 403


def test_locked_when_not_scheduled_even_if_kickoff_in_future(client, ctx, db):
    live = add_match(db, hours=1, status=MatchStatus.LIVE, home="Vivo")
    assert put(client, ctx["h"], ctx["gid"], live).status_code == 403
    done = add_match(db, hours=1, status=MatchStatus.FINISHED, home="Fin")
    assert put(client, ctx["h"], ctx["gid"], done).status_code == 403


def test_cannot_edit_after_kickoff_passes(client, ctx, db):
    put(client, ctx["h"], ctx["gid"], ctx["mid"], 2, 1)
    match = db.get(Match, ctx["mid"])
    match.kickoff_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert put(client, ctx["h"], ctx["gid"], ctx["mid"], 5, 5).status_code == 403
    mine = client.get(f"/groups/{ctx['gid']}/predictions", headers=ctx["h"]).json()
    assert (mine[0]["home_score"], mine[0]["away_score"]) == (2, 1)  # no cambió


def test_non_member_rejected(client, ctx):
    beto = signup(client, "beto")
    assert put(client, beto, ctx["gid"], ctx["mid"]).status_code == 404
    assert client.get(f"/groups/{ctx['gid']}/predictions", headers=beto).status_code == 404


def test_member_who_joined_by_invite_can_predict(client, ctx):
    beto = signup(client, "beto")
    code = make_invite(client, ctx["h"], ctx["gid"]).json()["code"]
    client.post("/groups/join", json={"code": code}, headers=beto)
    assert put(client, beto, ctx["gid"], ctx["mid"], 3, 3).status_code == 200


def test_match_from_other_competition_rejected(client, ctx, db):
    ucl = add_match(db, code="UCL", home="Madrid")
    assert put(client, ctx["h"], ctx["gid"], ucl).status_code == 422


def test_unknown_match(client, ctx):
    assert put(client, ctx["h"], ctx["gid"], 9999).status_code == 404


@pytest.mark.parametrize("home,away", [(-1, 0), (0, -1), (100, 0)])
def test_invalid_scores(client, ctx, home, away):
    assert put(client, ctx["h"], ctx["gid"], ctx["mid"], home, away).status_code == 422


def test_same_match_separate_per_group_and_per_user(client, ctx, db):
    ana, gid, mid = ctx["h"], ctx["gid"], ctx["mid"]
    gid2 = create(client, ana, name="Otro grupo", code="PL").json()["id"]
    beto = signup(client, "beto")
    code = make_invite(client, ana, gid).json()["code"]
    client.post("/groups/join", json={"code": code}, headers=beto)

    put(client, ana, gid, mid, 1, 0)
    put(client, ana, gid2, mid, 0, 3)
    put(client, beto, gid, mid, 2, 2)

    assert db.query(Prediction).count() == 3
    a1 = client.get(f"/groups/{gid}/predictions", headers=ana).json()
    a2 = client.get(f"/groups/{gid2}/predictions", headers=ana).json()
    b1 = client.get(f"/groups/{gid}/predictions", headers=beto).json()
    assert [(p["home_score"], p["away_score"]) for p in (a1[0], a2[0], b1[0])] == [
        (1, 0),
        (0, 3),
        (2, 2),
    ]


def test_list_only_mine_ordered_by_kickoff(client, ctx, db):
    later = add_match(db, hours=72, home="Later")
    put(client, ctx["h"], ctx["gid"], later, 1, 1)
    put(client, ctx["h"], ctx["gid"], ctx["mid"], 2, 0)
    mine = client.get(f"/groups/{ctx['gid']}/predictions", headers=ctx["h"]).json()
    assert [p["home_team"] for p in mine] == ["Arsenal", "Later"]
