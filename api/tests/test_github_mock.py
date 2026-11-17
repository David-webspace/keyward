import json
import re

from tests.conftest import gh_headers

ORG = "arcwell-demo"


def walk(client, url, headers):
    items = []
    while url:
        r = client.get(url, headers=headers)
        assert r.status_code == 200, r.text
        items += r.json()
        m = re.search(r'<([^>]+)>; rel="next"', r.headers.get("Link", ""))
        url = m.group(1) if m else None
    return items


def test_bad_token(client):
    assert client.get(f"/github/orgs/{ORG}/members", headers={"Authorization": "Bearer nope"}).status_code == 401


def test_link_pagination_returns_all_members(client, world_dir):
    gh = json.loads((world_dir / "github.json").read_text())
    items = walk(client, f"/github/orgs/{ORG}/members?per_page=20", gh_headers())
    assert sorted(m["login"] for m in items) == sorted(m["login"] for m in gh["members"])
    assert "name" not in items[0]  # 成員清單只有精簡欄位，姓名要另外查 /users/{login}


def test_2fa_filter_matches_truth(client, truth):
    items = walk(client, f"/github/orgs/{ORG}/members?filter=2fa_disabled&per_page=100", gh_headers())
    assert {m["login"] for m in items} == {i["account"] for i in truth["issues"] if i["type"] == "github_no_2fa"}


def test_read_token_cannot_remove(client, truth):
    login = next(i["account"] for i in truth["issues"] if i["type"] == "unlinked_github" and i["kind"] == "member")
    assert client.delete(f"/github/orgs/{ORG}/members/{login}", headers=gh_headers()).status_code == 403


def test_remove_member_and_reinvite_is_only_pending(client, truth):
    login = next(i["account"] for i in truth["issues"] if i["type"] == "terminated_github")
    assert client.delete(f"/github/orgs/{ORG}/members/{login}", headers=gh_headers(admin=True)).status_code == 204
    assert client.get(f"/github/orgs/{ORG}/members/{login}", headers=gh_headers()).status_code == 404
    r = client.put(f"/github/orgs/{ORG}/memberships/{login}", json={"role": "member"}, headers=gh_headers(admin=True))
    assert r.json()["state"] == "pending"
    assert client.get(f"/github/orgs/{ORG}/members/{login}", headers=gh_headers()).status_code == 404


def test_remove_outside_collaborator(client, truth):
    login = next(i["account"] for i in truth["issues"] if i["type"] == "unlinked_github" and i["kind"] == "outside_collaborator")
    assert client.delete(f"/github/orgs/{ORG}/outside_collaborators/{login}", headers=gh_headers(admin=True)).status_code == 204
    assert login not in {m["login"] for m in walk(client, f"/github/orgs/{ORG}/outside_collaborators", gh_headers())}


def test_user_profile_and_wrong_org(client, world_dir):
    gh = json.loads((world_dir / "github.json").read_text())
    m = gh["members"][0]
    body = client.get(f"/github/users/{m['login']}", headers=gh_headers()).json()
    assert body["name"] == m["name"] and body["email"] == m["email"]
    assert client.get("/github/orgs/someone-else/members", headers=gh_headers()).status_code == 404
