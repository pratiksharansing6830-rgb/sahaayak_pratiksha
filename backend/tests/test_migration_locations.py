from tests.helpers import auth_headers, create_family, create_migration, make_user

API = "/api/v1"


def _family(client, db):
    make_user(db, "loc@example.com")
    h = auth_headers(client, "loc@example.com")
    return h, create_family(client, h)


def _body(**o):
    b = {"origin_district": "Beed", "origin_state": "Maharashtra",
         "destination_district": "Pune", "destination_state": "Maharashtra"}
    b.update(o)
    return b


def test_destination_is_stored_in_canonical_form(client, db):
    h, fam = _family(client, db)
    m = create_migration(client, h, fam["id"], destination_district="pune", destination_state="maharashtra")
    assert m["destination_district"] == "Pune" and m["destination_state"] == "Maharashtra"


def test_unknown_destination_is_refused_not_defaulted(client, db):
    h, fam = _family(client, db)
    url = f"{API}/families/{fam['id']}/migrations"
    r = client.post(url, headers=h, json=_body(destination_district="Punee"))
    assert r.status_code == 422
    assert r.json()["detail"]["code"] == "LOCATION_NOT_RECOGNISED"
    assert "Pune" in r.json()["detail"]["suggestions"]
    assert client.get(url, headers=h).json() == []


def test_destination_outside_maharashtra_is_refused(client, db):
    h, fam = _family(client, db)
    r = client.post(f"{API}/families/{fam['id']}/migrations", headers=h,
                    json=_body(destination_district="Pune", destination_state="Karnataka"))
    assert r.status_code == 422 and r.json()["detail"]["code"] == "STATE_NOT_SUPPORTED"


def test_editing_destination_is_checked_but_origin_is_free(client, db):
    h, fam = _family(client, db)
    m = create_migration(client, h, fam["id"])
    url = f"{API}/migrations/{m['id']}"
    assert client.patch(url, headers=h, json={"destination_district": "Atlantis"}).status_code == 422
    r = client.patch(url, headers=h, json={"destination_district": "nagpur"})
    assert r.status_code == 200 and r.json()["destination_district"] == "Nagpur"
    r = client.patch(url, headers=h, json={"origin_district": "Gaya", "origin_state": "Bihar"})
    assert r.status_code == 200 and r.json()["origin_state"] == "Bihar"