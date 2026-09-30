from datetime import UTC, datetime, timedelta

from app.models import Invite
from tests.test_groups import create, signup


def make_invite(client, headers, gid, **body):
    return client.post(f"/groups/{gid}/invites", json=body, headers=headers)


def test_member_creates_invite(client):
    ana = signup(client, "ana")
    gid = create(client, ana).json()["id"]
    r = make_invite(client, ana, gid)
    assert r.status_code == 201
    body = r.json()
    assert len(body["code"]) == 8
    assert body["group_id"] == gid
    assert body["expires_at"] is not None  # por defecto expira (7 días)


def test_invite_without_expiration(client):
    ana = signup(client, "ana")
    gid = create(client, ana).json()["id"]
    r = make_invite(client, ana, gid, expires_in_hours=None)
    assert r.json()["expires_at"] is None


def test_non_member_cannot_create_invite(client):
    ana, beto = signup(client, "ana"), signup(client, "beto")
    gid = create(client, ana).json()["id"]
    assert make_invite(client, beto, gid).status_code == 404
    assert make_invite(client, ana, 9999).status_code == 404


def test_invite_requires_auth_and_valid_ttl(client):
    ana = signup(client, "ana")
    gid = create(client, ana).json()["id"]
    assert client.post(f"/groups/{gid}/invites", json={}).status_code == 401
    assert make_invite(client, ana, gid, expires_in_hours=0).status_code == 422


def test_join_with_code(client):
    ana, beto = signup(client, "ana"), signup(client, "beto")
    gid = create(client, ana).json()["id"]
    code = make_invite(client, ana, gid).json()["code"]
    r = client.post("/groups/join", json={"code": code.lower()}, headers=beto)
    assert r.status_code == 200
    assert r.json()["id"] == gid
    assert r.json()["member_count"] == 2
    # ahora beto ve el grupo y aparece en la lista
    assert client.get(f"/groups/{gid}", headers=beto).status_code == 200
    assert [g["id"] for g in client.get("/groups", headers=beto).json()] == [gid]


def test_code_is_reusable_by_many_users(client):
    ana = signup(client, "ana")
    gid = create(client, ana).json()["id"]
    code = make_invite(client, ana, gid).json()["code"]
    for name in ("beto", "caro", "dani"):
        r = client.post("/groups/join", json={"code": code}, headers=signup(client, name))
        assert r.status_code == 200
    assert client.get(f"/groups/{gid}", headers=ana).json()["member_count"] == 4


def test_join_twice_conflicts(client):
    ana, beto = signup(client, "ana"), signup(client, "beto")
    gid = create(client, ana).json()["id"]
    code = make_invite(client, ana, gid).json()["code"]
    assert client.post("/groups/join", json={"code": code}, headers=beto).status_code == 200
    assert client.post("/groups/join", json={"code": code}, headers=beto).status_code == 409
    # el dueño tampoco puede unirse a su propio grupo otra vez
    assert client.post("/groups/join", json={"code": code}, headers=ana).status_code == 409
    assert client.get(f"/groups/{gid}", headers=ana).json()["member_count"] == 2


def test_join_unknown_code(client):
    beto = signup(client, "beto")
    assert client.post("/groups/join", json={"code": "NOEXISTE"}, headers=beto).status_code == 404


def test_join_expired_code(client, db):
    ana, beto = signup(client, "ana"), signup(client, "beto")
    gid = create(client, ana).json()["id"]
    code = make_invite(client, ana, gid).json()["code"]
    invite = db.query(Invite).filter_by(code=code).one()
    invite.expires_at = datetime.now(UTC) - timedelta(minutes=1)
    db.commit()
    assert client.post("/groups/join", json={"code": code}, headers=beto).status_code == 410
    assert client.get(f"/groups/{gid}", headers=beto).status_code == 404  # no quedó dentro


def test_join_requires_auth(client):
    assert client.post("/groups/join", json={"code": "ABC"}).status_code == 401
