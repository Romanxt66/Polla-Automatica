def signup(client, username: str) -> dict:
    client.post(
        "/auth/register",
        json={"email": f"{username}@example.com", "username": username, "password": "clave12345"},
    )
    r = client.post(
        "/auth/login", json={"email": f"{username}@example.com", "password": "clave12345"}
    )
    return {"Authorization": f"Bearer {r.json()['access_token']}"}


def create(client, headers, name="Los parceros", code="PL"):
    return client.post("/groups", json={"name": name, "competition_code": code}, headers=headers)


def test_requires_auth(client):
    assert client.get("/groups").status_code == 401
    assert client.post("/groups", json={"name": "x", "competition_code": "PL"}).status_code == 401
    assert client.get("/groups/1").status_code == 401


def test_create_group_makes_owner_a_member(client):
    h = signup(client, "ana")
    r = create(client, h, code="pl")  # código en minúsculas se normaliza
    assert r.status_code == 201
    body = r.json()
    assert body["name"] == "Los parceros"
    assert body["competition_code"] == "PL"
    assert body["member_count"] == 1
    assert body["owner_id"] == client.get("/auth/me", headers=h).json()["id"]


def test_create_group_unknown_competition(client):
    h = signup(client, "ana")
    assert create(client, h, code="XYZ").status_code == 404


def test_create_group_validation(client):
    h = signup(client, "ana")
    assert create(client, h, name="   ").status_code == 422
    assert create(client, h, name="x" * 101).status_code == 422


def test_list_only_my_groups(client):
    ana, beto = signup(client, "ana"), signup(client, "beto")
    create(client, ana, name="De Ana")
    create(client, beto, name="De Beto", code="UCL")
    mine = client.get("/groups", headers=ana).json()
    assert [g["name"] for g in mine] == ["De Ana"]
    assert client.get("/groups", headers=signup(client, "caro")).json() == []


def test_get_group_detail_for_member(client):
    h = signup(client, "ana")
    gid = create(client, h).json()["id"]
    r = client.get(f"/groups/{gid}", headers=h)
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == gid
    assert [m["username"] for m in body["members"]] == ["ana"]


def test_get_group_hidden_from_non_member(client):
    ana, beto = signup(client, "ana"), signup(client, "beto")
    gid = create(client, ana).json()["id"]
    assert client.get(f"/groups/{gid}", headers=beto).status_code == 404
    assert client.get("/groups/9999", headers=ana).status_code == 404
