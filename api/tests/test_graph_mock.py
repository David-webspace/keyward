from tests.conftest import graph_token


def walk(client, url, headers):
    items, pages = [], 0
    while url:
        r = client.get(url, headers=headers)
        assert r.status_code == 200, r.text
        body = r.json()
        items += body["value"]
        pages += 1
        url = body.get("@odata.nextLink")
    return items, pages, body


def find(entra, upn):
    return next(u for u in entra["users"] if u["userPrincipalName"] == upn)


def test_token_rejects_bad_secret(client):
    r = client.post("/login/arcwell/oauth2/v2.0/token", data={"client_id": "x", "client_secret": "y",
                                                             "grant_type": "client_credentials",
                                                             "scope": "https://graph.microsoft.com/.default"})
    assert r.status_code == 401 and r.json()["error"] == "invalid_client"


def test_requires_token(client):
    r = client.get("/v1.0/users")
    assert r.status_code == 401 and r.json()["error"]["code"] == "InvalidAuthenticationToken"


def test_paging_covers_every_user_once(client, entra):
    items, pages, _ = walk(client, "/v1.0/users?$top=50&$select=userPrincipalName,accountEnabled", graph_token(client))
    assert pages == -(-len(entra["users"]) // 50)
    assert sorted(u["id"] for u in items) == sorted(u["id"] for u in entra["users"])


def test_default_properties_hide_account_enabled(client):
    u = client.get("/v1.0/users?$top=1", headers=graph_token(client)).json()["value"][0]
    assert "accountEnabled" not in u and "userPrincipalName" in u


def test_sign_in_activity_caps_page_size_at_120(client):
    body = client.get("/v1.0/users?$top=999&$select=signInActivity", headers=graph_token(client)).json()
    assert len(body["value"]) == 120 and "@odata.nextLink" in body


def test_sign_in_activity_needs_premium(client):
    client.put("/_mock/faults", json={"premium": False})
    r = client.get("/v1.0/users?$select=signInActivity", headers=graph_token(client))
    assert r.status_code == 403 and r.json()["error"]["code"] == "Authentication_RequestFromNonPremiumTenantOrB2CTenant"


def test_unknown_select_is_rejected(client):
    r = client.get("/v1.0/users?$select=salary", headers=graph_token(client))
    assert r.status_code == 400


def test_reader_cannot_write_and_writer_cannot_list_groups(client, entra):
    uid = entra["users"][10]["id"]
    r = client.patch(f"/v1.0/users/{uid}", json={"accountEnabled": False}, headers=graph_token(client))
    assert r.status_code == 403 and r.json()["error"]["code"] == "Authorization_RequestDenied"
    assert client.get("/v1.0/groups", headers=graph_token(client, writer=True)).status_code == 403


def test_disable_then_users_delta_returns_only_that_user(client, truth, entra):
    reader, writer = graph_token(client), graph_token(client, writer=True)
    _, _, last = walk(client, "/v1.0/users/delta?$select=userPrincipalName,accountEnabled", reader)
    delta_link = last["@odata.deltaLink"]
    upn = next(i["account"] for i in truth["issues"] if i["type"] == "terminated_enabled")
    target = find(entra, upn)
    assert client.patch(f"/v1.0/users/{target['id']}", json={"accountEnabled": False}, headers=writer).status_code == 204
    changes, _, last2 = walk(client, delta_link, reader)
    assert changes == [{"id": target["id"], "userPrincipalName": upn, "accountEnabled": False}]
    again, _, _ = walk(client, last2["@odata.deltaLink"], reader)
    assert again == []


def test_cannot_disable_privileged_user(client, entra):
    admin_id = entra["roleAssignments"][0]["principalId"]
    r = client.patch(f"/v1.0/users/{admin_id}", json={"accountEnabled": False}, headers=graph_token(client, writer=True))
    assert r.status_code == 403


def test_remove_member_shows_in_groups_delta_and_can_be_restored(client, truth, entra):
    reader, writer = graph_token(client), graph_token(client, writer=True)
    issue = next(i for i in truth["issues"] if i["type"] == "transfer_residual")
    gid = next(g["id"] for g in entra["groups"] if g["displayName"] == issue["group"])
    uid = find(entra, issue["account"])["id"]
    _, _, last = walk(client, "/v1.0/groups/delta?$select=displayName,members", reader)
    assert client.delete(f"/v1.0/groups/{gid}/members/{uid}/$ref", headers=writer).status_code == 204
    assert client.delete(f"/v1.0/groups/{gid}/members/{uid}/$ref", headers=writer).status_code == 404
    changes, _, _ = walk(client, last["@odata.deltaLink"], reader)
    assert changes == [{"id": gid, "members@delta": [
        {"@odata.type": "#microsoft.graph.user", "id": uid, "@removed": {"reason": "deleted"}}]}]
    body = {"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{uid}"}
    assert client.post(f"/v1.0/groups/{gid}/members/$ref", json=body, headers=writer).status_code == 204
    assert client.post(f"/v1.0/groups/{gid}/members/$ref", json=body, headers=writer).status_code == 400


def test_transitive_membership_follows_nesting(client, truth, entra):
    issue = next(i for i in truth["issues"] if i["type"] == "launch_overprovisioned")
    uid = find(entra, issue["account"])["id"]
    items, _, _ = walk(client, f"/v1.0/users/{uid}/transitiveMemberOf", graph_token(client))
    names = {g["displayName"] for g in items}
    assert {"TMP-CBI-Launch", *issue["grants"]} <= names


def test_delete_guest_and_restore(client, truth, entra):
    reader, writer = graph_token(client), graph_token(client, writer=True)
    guest = find(entra, next(i["account"] for i in truth["issues"] if i["type"] == "guest_access"))
    assert client.delete(f"/v1.0/users/{guest['id']}", headers=writer).status_code == 204
    assert client.get(f"/v1.0/users/{guest['id']}", headers=reader).status_code == 404
    deleted, _, _ = walk(client, "/v1.0/directory/deletedItems/microsoft.graph.user", reader)
    assert [u["id"] for u in deleted] == [guest["id"]]
    assert client.post(f"/v1.0/directory/deletedItems/{guest['id']}/restore", headers=writer).status_code == 200
    assert client.get(f"/v1.0/users/{guest['id']}", headers=reader).status_code == 200


def test_throttle_returns_retry_after(client):
    headers = graph_token(client)
    client.put("/_mock/faults", json={"throttle_every": 3, "retry_after": 2})
    codes = [client.get("/v1.0/users?$top=1", headers=headers) for _ in range(6)]
    throttled = [r for r in codes if r.status_code == 429]
    assert len(throttled) == 2 and throttled[0].headers["Retry-After"] == "2"


def test_failed_write_is_not_applied(client, entra):
    writer, reader = graph_token(client, writer=True), graph_token(client)
    uid = next(u["id"] for u in entra["users"] if u["userType"] == "Member" and u["accountEnabled"]
               and u["id"] not in {a["principalId"] for a in entra["roleAssignments"]})
    client.put("/_mock/faults", json={"fail_writes": [1]})
    assert client.patch(f"/v1.0/users/{uid}", json={"accountEnabled": False}, headers=writer).status_code == 503
    assert client.get(f"/v1.0/users/{uid}?$select=accountEnabled", headers=reader).json()["accountEnabled"] is True


def test_silent_write_reports_success_but_changes_nothing(client, entra):
    writer, reader = graph_token(client, writer=True), graph_token(client)
    uid = next(u["id"] for u in entra["users"] if u["userType"] == "Member" and u["accountEnabled"]
               and u["id"] not in {a["principalId"] for a in entra["roleAssignments"]})
    client.put("/_mock/faults", json={"silent_ids": [uid]})
    assert client.patch(f"/v1.0/users/{uid}", json={"accountEnabled": False}, headers=writer).status_code == 204
    assert client.get(f"/v1.0/users/{uid}?$select=accountEnabled", headers=reader).json()["accountEnabled"] is True


def test_role_assignment_filter_and_delete(client, truth, entra):
    reader, writer = graph_token(client), graph_token(client, writer=True)
    issue = next(i for i in truth["issues"] if i["type"] == "excess_admin")
    uid = find(entra, issue["account"])["id"]
    items = client.get(f"/v1.0/roleManagement/directory/roleAssignments?$filter=principalId eq '{uid}'",
                       headers=reader).json()["value"]
    assert len(items) == 1
    assert client.delete(f"/v1.0/roleManagement/directory/roleAssignments/{items[0]['id']}", headers=writer).status_code == 204
    assert client.get(f"/v1.0/roleManagement/directory/roleAssignments?$filter=principalId eq '{uid}'",
                      headers=reader).json()["value"] == []
