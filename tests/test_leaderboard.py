import pytest

from app.models import PointsLedger, Prediction, User
from tests.test_groups import create, signup
from tests.test_invites import make_invite
from tests.test_predictions import add_match


def user_id(db, username):
    return db.query(User).filter_by(username=username).one().id


def score(db, gid, match_id, username, points, exact=False):
    uid = user_id(db, username)
    pred = Prediction(user_id=uid, group_id=gid, match_id=match_id, home_score=1, away_score=0)
    db.add(pred)
    db.flush()
    db.add(
        PointsLedger(
            prediction_id=pred.id,
            user_id=uid,
            group_id=gid,
            match_id=match_id,
            points=points,
            is_exact=exact,
        )
    )
    db.commit()


@pytest.fixture()
def ctx(client, db):
    ana = signup(client, "ana")
    gid = create(client, ana).json()["id"]
    code = make_invite(client, ana, gid).json()["code"]
    heads = {"ana": ana}
    for name in ("beto", "caro"):
        heads[name] = signup(client, name)
        client.post("/groups/join", json={"code": code}, headers=heads[name])
    matches = [add_match(db, home=f"T{i}") for i in range(3)]
    return {"h": heads, "gid": gid, "m": matches}


def board(client, ctx, who="ana"):
    r = client.get(f"/groups/{ctx['gid']}/leaderboard", headers=ctx["h"][who])
    assert r.status_code == 200
    return r.json()


def test_requires_auth_and_membership(client, ctx):
    assert client.get(f"/groups/{ctx['gid']}/leaderboard").status_code == 401
    dani = signup(client, "dani")
    assert client.get(f"/groups/{ctx['gid']}/leaderboard", headers=dani).status_code == 404
    assert client.get("/groups/9999/leaderboard", headers=dani).status_code == 404


def test_everyone_zero_before_any_match_finishes(client, ctx):
    rows = board(client, ctx)
    assert [r["username"] for r in rows] == ["ana", "beto", "caro"]  # desempate alfabético
    assert all(r["points"] == 0 and r["rank"] == 1 for r in rows)


def test_sums_points_and_orders(client, ctx, db):
    gid, m = ctx["gid"], ctx["m"]
    score(db, gid, m[0], "ana", 1)
    score(db, gid, m[1], "ana", 1)
    score(db, gid, m[0], "beto", 5, exact=True)
    score(db, gid, m[1], "caro", 3)
    rows = board(client, ctx)
    assert [(r["username"], r["points"], r["rank"]) for r in rows] == [
        ("beto", 5, 1),
        ("caro", 3, 2),
        ("ana", 2, 3),
    ]
    beto = rows[0]
    assert beto["exact_hits"] == 1 and beto["scored_predictions"] == 1
    assert rows[2]["scored_predictions"] == 2


def test_tie_broken_by_exact_hits_and_shared_rank(client, ctx, db):
    gid, m = ctx["gid"], ctx["m"]
    score(db, gid, m[0], "ana", 5, exact=True)
    score(db, gid, m[0], "beto", 3)
    score(db, gid, m[1], "beto", 2)  # beto: 5 pts, 0 exactos -> pierde ante ana
    score(db, gid, m[0], "caro", 5, exact=True)  # empata con ana en todo
    rows = board(client, ctx)
    assert [(r["username"], r["rank"]) for r in rows] == [
        ("ana", 1),
        ("caro", 1),
        ("beto", 3),
    ]


def test_points_are_isolated_per_group(client, ctx, db):
    m = ctx["m"]
    other = create(client, ctx["h"]["ana"], name="Otro", code="PL").json()["id"]
    score(db, other, m[0], "ana", 5, exact=True)
    assert all(r["points"] == 0 for r in board(client, ctx))
    assert board_other(client, ctx, other)[0]["points"] == 5


def board_other(client, ctx, gid):
    return client.get(f"/groups/{gid}/leaderboard", headers=ctx["h"]["ana"]).json()
