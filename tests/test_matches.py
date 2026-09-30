from datetime import UTC, datetime, timedelta

import pytest

from app.models import Competition, Match, MatchStatus
from tests.test_groups import signup

NOW = datetime(2026, 10, 1, 12, tzinfo=UTC)


@pytest.fixture()
def seeded(db):
    comp = {c.code: c for c in db.query(Competition)}
    rows = [
        ("PL", "Arsenal", "Chelsea", 2, MatchStatus.FINISHED, 2, 1),
        ("PL", "Liverpool", "Everton", 5, MatchStatus.SCHEDULED, None, None),
        ("PL", "City", "United", 3, MatchStatus.SCHEDULED, None, None),
        ("UCL", "Real Madrid", "Bayern", 4, MatchStatus.SCHEDULED, None, None),
        ("BETPLAY", "Nacional", "Millonarios", 1, MatchStatus.LIVE, 0, 0),
    ]
    for i, (code, home, away, days, st, hs, as_) in enumerate(rows):
        db.add(
            Match(
                external_id=f"ext-{i}",
                competition_id=comp[code].id,
                home_team=home,
                away_team=away,
                kickoff_at=NOW + timedelta(days=days),
                status=st,
                home_score=hs,
                away_score=as_,
            )
        )
    db.commit()


def teams(resp):
    return [m["home_team"] for m in resp.json()]


def test_requires_auth(client):
    assert client.get("/matches").status_code == 401
    assert client.get("/matches/1").status_code == 401
    assert client.get("/competitions").status_code == 401


def test_list_competitions(client):
    h = signup(client, "ana")
    r = client.get("/competitions", headers=h)
    assert [c["code"] for c in r.json()] == ["BETPLAY", "UCL", "PL"]


def test_list_all_ordered_by_kickoff(client, seeded):
    h = signup(client, "ana")
    r = client.get("/matches", headers=h)
    assert r.status_code == 200
    assert teams(r) == ["Nacional", "Arsenal", "City", "Real Madrid", "Liverpool"]


def test_filter_by_competition(client, seeded):
    h = signup(client, "ana")
    r = client.get("/matches?competition=pl", headers=h)
    assert teams(r) == ["Arsenal", "City", "Liverpool"]
    assert teams(client.get("/matches?competition=UCL", headers=h)) == ["Real Madrid"]
    assert client.get("/matches?competition=NOPE", headers=h).json() == []


def test_filter_by_status(client, seeded):
    h = signup(client, "ana")
    assert teams(client.get("/matches?status=FINISHED", headers=h)) == ["Arsenal"]
    assert len(client.get("/matches?status=SCHEDULED", headers=h).json()) == 3
    assert client.get("/matches?status=INVENTADO", headers=h).status_code == 422


def test_filter_by_date_range(client, seeded):
    h = signup(client, "ana")
    start = (NOW + timedelta(days=3)).isoformat()
    end = (NOW + timedelta(days=5)).isoformat()
    r = client.get("/matches", params={"date_from": start, "date_to": end}, headers=h)
    assert teams(r) == ["City", "Real Madrid"]  # [from, to)


def test_pagination(client, seeded):
    h = signup(client, "ana")
    page1 = client.get("/matches?limit=2", headers=h)
    page2 = client.get("/matches?limit=2&offset=2", headers=h)
    assert teams(page1) == ["Nacional", "Arsenal"]
    assert teams(page2) == ["City", "Real Madrid"]
    assert client.get("/matches?limit=0", headers=h).status_code == 422
    assert client.get("/matches?limit=500", headers=h).status_code == 422


def test_match_shape_and_detail(client, seeded):
    h = signup(client, "ana")
    finished = client.get("/matches?status=FINISHED", headers=h).json()[0]
    assert finished["competition_code"] == "PL"
    assert (finished["home_score"], finished["away_score"]) == (2, 1)
    r = client.get(f"/matches/{finished['id']}", headers=h)
    assert r.status_code == 200 and r.json() == finished
    assert client.get("/matches/9999", headers=h).status_code == 404
