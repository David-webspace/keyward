"""Microsoft Graph v1.0 的 mock。

只實作 keyward 用到的端點；回應格式、分頁（@odata.nextLink）、delta query、應用程式權限、錯誤碼依照官方文件：
- 選 signInActivity 需要 AuditLog.Read.All 與 P1/P2 授權，且每頁最多 120 筆
- 修改 accountEnabled 需要 User.EnableDisableAccount.All + User.Read.All；目標若擔任管理員角色，App 本身還得有更高的角色
"""

import re
import secrets
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Form, Request
from fastapi.responses import JSONResponse, Response

from app.mock.state import Store, WriteFailed, dec, enc

GRAPH_ROOT = "https://graph.microsoft.com/v1.0"
USER_DEFAULT = ["businessPhones", "displayName", "givenName", "jobTitle", "mail", "mobilePhone", "officeLocation",
                "preferredLanguage", "surname", "userPrincipalName"]
USER_FIELDS = set(USER_DEFAULT) | {"accountEnabled", "employeeId", "employeeType", "employeeHireDate", "department",
                                   "companyName", "usageLocation", "userType", "createdDateTime", "externalUserState",
                                   "signInActivity"}
GROUP_FIELDS = {"displayName", "description", "mailEnabled", "mailNickname", "securityEnabled", "groupTypes",
                "createdDateTime", "visibility"}


class GraphError(Exception):
    def __init__(self, status: int, code: str, message: str, headers: dict | None = None):
        self.status, self.code, self.message, self.headers = status, code, message, headers


def error_body(code: str, message: str) -> dict:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")
    return {"error": {"code": code, "message": message,
                      "innerError": {"date": now, "request-id": str(uuid.uuid4()), "client-request-id": str(uuid.uuid4())}}}


def denied() -> GraphError:
    return GraphError(403, "Authorization_RequestDenied", "Insufficient privileges to complete the operation.")


def store_of(request: Request) -> Store:
    return request.app.state.store


def require(request: Request, *need: str | tuple[str, ...]) -> set[str]:
    """need 裡的字串都要有；tuple 代表其中一個即可。"""
    auth = request.headers.get("authorization", "")
    roles = store_of(request).tokens.get(auth.removeprefix("Bearer ").strip()) if auth.startswith("Bearer ") else None
    if roles is None:
        raise GraphError(401, "InvalidAuthenticationToken", "Access token is empty or invalid.")
    for n in need:
        if (isinstance(n, tuple) and not roles.intersection(n)) or (isinstance(n, str) and n not in roles):
            raise denied()
    return roles


def parse_select(request: Request, allowed: set[str], type_name: str) -> list[str] | None:
    raw = request.query_params.get("$select")
    if not raw:
        return None
    fields = [f.strip() for f in raw.split(",") if f.strip()]
    for f in fields:
        if f not in allowed and f != "id":
            raise GraphError(400, "Request_BadRequest", f"Could not find a property named '{f}' on type '{type_name}'.")
    return fields


def project(obj: dict, fields: list[str]) -> dict:
    out = {"id": obj["id"]}
    for f in fields:
        if f != "id":
            out[f] = obj.get(f)
    return out


def page_size(request: Request, default: int, maximum: int) -> int:
    raw = request.query_params.get("$top")
    if raw is None:
        return default
    if not raw.isdigit() or int(raw) < 1:
        raise GraphError(400, "Request_BadRequest", "Invalid page size specified.")
    return min(int(raw), maximum)


def paged(request: Request, context: str, items: list[dict], top: int, extra: dict | None = None) -> dict:
    skip = request.query_params.get("$skiptoken")
    offset = dec(skip)["o"] if skip else 0
    chunk = items[offset:offset + top]
    body = {"@odata.context": f"{GRAPH_ROOT}/$metadata#{context}", "value": chunk}
    if offset + top < len(items):
        body["@odata.nextLink"] = str(request.url.include_query_params(**{"$skiptoken": enc({"o": offset + top, **(extra or {})})}))
    return body


def member_ref(store: Store, mid: str) -> dict | None:
    if mid in store.users:
        u = store.users[mid]
        return {"@odata.type": "#microsoft.graph.user", "id": mid, "displayName": u["displayName"],
                "userPrincipalName": u["userPrincipalName"]}
    if mid in store.groups:
        return {"@odata.type": "#microsoft.graph.group", "id": mid, "displayName": store.groups[mid]["displayName"]}
    return None


def transitive(store: Store, gid: str) -> list[str]:
    seen, out, stack = {gid}, [], list(store.members.get(gid, []))
    while stack:
        mid = stack.pop(0)
        if mid in seen:
            continue
        seen.add(mid)
        if mid in store.users or mid in store.groups:
            out.append(mid)
        if mid in store.groups:
            stack += store.members.get(mid, [])
    return out


def user_select(request: Request, store: Store) -> tuple[list[str], bool]:
    fields = parse_select(request, USER_FIELDS, "microsoft.graph.user") or USER_DEFAULT
    with_sign_in = "signInActivity" in fields
    if with_sign_in:
        require(request, "AuditLog.Read.All")
        if not store.faults.premium:
            raise GraphError(403, "Authentication_RequestFromNonPremiumTenantOrB2CTenant",
                             "Neither tenant is B2C or tenant doesn't have premium license")
    return fields, with_sign_in


def get_user(store: Store, key: str) -> dict:
    u = store.find_user(key)
    if u is None:
        raise GraphError(404, "Request_ResourceNotFound", f"Resource '{key}' does not exist or one of its queried reference-property objects are not present.")
    return u


def get_group(store: Store, gid: str) -> dict:
    if gid not in store.groups:
        raise GraphError(404, "Request_ResourceNotFound", f"Resource '{gid}' does not exist or one of its queried reference-property objects are not present.")
    return store.groups[gid]


def gate(store: Store, target: str) -> bool:
    try:
        return store.write_gate(target)
    except WriteFailed:
        raise GraphError(503, "serviceNotAvailable", "Service unavailable. Please retry.", {"Retry-After": "1"})


def is_privileged(store: Store, uid: str) -> bool:
    return any(a["principalId"] == uid for a in store.role_assignments.values())


router = APIRouter()


@router.post("/login/{tenant}/oauth2/v2.0/token")
def token(request: Request, tenant: str, client_id: str = Form(...), client_secret: str = Form(...),
          grant_type: str = Form(...), scope: str = Form(...)):
    client = request.app.state.graph_clients.get(client_id)
    if grant_type != "client_credentials":
        return JSONResponse({"error": "unsupported_grant_type"}, 400)
    if client is None or not secrets.compare_digest(client[0], client_secret):
        return JSONResponse({"error": "invalid_client",
                             "error_description": "AADSTS7000215: Invalid client secret provided."}, 401)
    if scope != "https://graph.microsoft.com/.default":
        return JSONResponse({"error": "invalid_scope"}, 400)
    tok = secrets.token_urlsafe(32)
    store_of(request).tokens[tok] = set(client[1])
    return {"token_type": "Bearer", "expires_in": 3599, "ext_expires_in": 3599, "access_token": tok}


# ---------- 使用者 ----------

@router.get("/v1.0/users")
def list_users(request: Request):
    store = store_of(request)
    require(request, "User.Read.All")
    fields, with_sign_in = user_select(request, store)
    items = list(store.users.values())
    flt = request.query_params.get("$filter")
    if flt:
        m = re.fullmatch(r"(accountEnabled) eq (true|false)|(userType) eq '(Member|Guest)'", flt.strip())
        if not m:
            raise GraphError(400, "Request_UnsupportedQuery", "Unsupported or invalid query filter clause specified.")
        if m.group(1):
            items = [u for u in items if u["accountEnabled"] == (m.group(2) == "true")]
        else:
            items = [u for u in items if u["userType"] == m.group(4)]
    top = page_size(request, 100, 120 if with_sign_in else 999)
    return paged(request, "users", [project(u, fields) for u in items], top)


@router.get("/v1.0/users/delta")
def users_delta(request: Request):
    store = store_of(request)
    require(request, "User.Read.All")
    fields, with_sign_in = user_select(request, store)
    if with_sign_in:  # 真實 Graph 的 users/delta 不支援 signInActivity，要另外用 /users 讀
        raise GraphError(400, "Request_UnsupportedQuery", "Unsupported query: signInActivity is not supported with delta.")
    skip, delta = request.query_params.get("$skiptoken"), request.query_params.get("$deltatoken")
    state = dec(skip) if skip else ({"since": dec(delta)["v"]} if delta else {})
    if "since" in state:
        changed: dict[str, None] = {}
        for v, uid in store.user_log:
            if state["since"] < v <= state.get("until", store.version):
                changed.pop(uid, None)
                changed[uid] = None
        items = [project(store.users[uid], fields) if uid in store.users
                 else {"id": uid, "@removed": {"reason": "changed"}} for uid in changed]
        until = state.get("until", store.version)
    else:
        until = state.get("until", store.version)
        items = [project(u, fields) for u in store.users.values()]
    return delta_page(request, "users", items, state, until)


def delta_page(request: Request, context: str, items: list[dict], state: dict, until: int) -> dict:
    offset, top = state.get("o", 0), 200
    chunk = items[offset:offset + top]
    body = {"@odata.context": f"{GRAPH_ROOT}/$metadata#{context}", "value": chunk}
    base = request.url.remove_query_params(["$skiptoken", "$deltatoken"])
    if offset + top < len(items):
        nxt = {k: v for k, v in state.items() if k != "o"} | {"o": offset + top, "until": until}
        body["@odata.nextLink"] = str(base.include_query_params(**{"$skiptoken": enc(nxt)}))
    else:
        body["@odata.deltaLink"] = str(base.include_query_params(**{"$deltatoken": enc({"v": until})}))
    return body


@router.get("/v1.0/users/{key}")
def read_user(request: Request, key: str):
    store = store_of(request)
    require(request, "User.Read.All")
    fields, _ = user_select(request, store)
    return {"@odata.context": f"{GRAPH_ROOT}/$metadata#users/$entity", **project(get_user(store, key), fields)}


@router.patch("/v1.0/users/{key}")
async def update_user(request: Request, key: str):
    store = store_of(request)
    roles = require(request, "User.Read.All")
    body = await request.json()
    if set(body) != {"accountEnabled"} or not isinstance(body["accountEnabled"], bool):
        if "User.ReadWrite.All" not in roles:
            raise denied()
    if "User.EnableDisableAccount.All" not in roles and "User.ReadWrite.All" not in roles:
        raise denied()
    u = get_user(store, key)
    if is_privileged(store, u["id"]):
        raise denied()  # 目標擔任管理員角色：App 需要更高的角色才能改，keyward 的寫入 App 刻意沒有
    if gate(store, u["id"]):
        u["accountEnabled"] = body["accountEnabled"]
        store.user_log.append((store.bump(), u["id"]))
    return Response(status_code=204)


@router.delete("/v1.0/users/{key}")
def delete_user(request: Request, key: str):
    store = store_of(request)
    require(request, ("User.DeleteRestore.All", "User.ReadWrite.All"))
    u = get_user(store, key)
    if is_privileged(store, u["id"]):
        raise denied()
    if gate(store, u["id"]):
        store.deleted_users[u["id"]] = store.users.pop(u["id"])
        store.deleted_users[u["id"]]["deletedDateTime"] = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        store.user_log.append((store.bump(), u["id"]))
    return Response(status_code=204)


@router.post("/v1.0/users/{key}/revokeSignInSessions")
def revoke_sessions(request: Request, key: str):
    store = store_of(request)
    require(request, ("User.RevokeSessions.All", "User.ReadWrite.All"))
    u = get_user(store, key)
    gate(store, u["id"])
    return {"@odata.context": f"{GRAPH_ROOT}/$metadata#Edm.Boolean", "value": True}


@router.get("/v1.0/users/{key}/memberOf")
def user_member_of(request: Request, key: str):
    store = store_of(request)
    require(request, "User.Read.All", ("Group.Read.All", "GroupMember.Read.All"))
    uid = get_user(store, key)["id"]
    items = [member_ref(store, gid) for gid, ms in store.members.items() if uid in ms]
    return paged(request, "directoryObjects", items, page_size(request, 100, 999))


@router.get("/v1.0/users/{key}/transitiveMemberOf")
def user_transitive_member_of(request: Request, key: str):
    store = store_of(request)
    require(request, "User.Read.All", ("Group.Read.All", "GroupMember.Read.All"))
    uid = get_user(store, key)["id"]
    items = [member_ref(store, gid) for gid in store.groups if uid in transitive(store, gid)]
    return paged(request, "directoryObjects", items, page_size(request, 100, 999))


# ---------- 群組 ----------

@router.get("/v1.0/groups")
def list_groups(request: Request):
    store = store_of(request)
    require(request, ("Group.Read.All", "GroupMember.Read.All"))
    fields = parse_select(request, GROUP_FIELDS, "microsoft.graph.group") or sorted(GROUP_FIELDS)
    return paged(request, "groups", [project(g, fields) for g in store.groups.values()], page_size(request, 100, 999))


@router.get("/v1.0/groups/delta")
def groups_delta(request: Request):
    store = store_of(request)
    require(request, ("Group.Read.All", "GroupMember.Read.All"))
    raw = [f.strip() for f in (request.query_params.get("$select") or "").split(",") if f.strip()]
    with_members = "members" in raw
    for f in raw:
        if f not in GROUP_FIELDS | {"id", "members"}:
            raise GraphError(400, "Request_BadRequest", f"Could not find a property named '{f}' on type 'microsoft.graph.group'.")
    fields = [f for f in raw if f != "members"] or sorted(GROUP_FIELDS)
    skip, delta = request.query_params.get("$skiptoken"), request.query_params.get("$deltatoken")
    state = dec(skip) if skip else ({"since": dec(delta)["v"]} if delta else {})
    until = state.get("until", store.version)

    def ref(mid: str) -> dict:
        return {"@odata.type": "#microsoft.graph.user" if mid in store.users or mid in store.deleted_users
                else "#microsoft.graph.group", "id": mid}

    if "since" in state:
        net: dict[str, dict[str, bool]] = {}
        for v, gid, mid, removed in store.member_log:
            if state["since"] < v <= until:
                net.setdefault(gid, {})[mid] = removed
        items = []
        for gid, changes in net.items():
            item = {"id": gid}
            if with_members:
                item["members@delta"] = [ref(mid) | ({"@removed": {"reason": "deleted"}} if removed else {})
                                         for mid, removed in changes.items()]
            items.append(item)
    else:
        items = []
        for g in store.groups.values():
            item = project(g, fields)
            if with_members:
                item["members@delta"] = [ref(mid) for mid in store.members[g["id"]] if member_ref(store, mid)]
            items.append(item)
    return delta_page(request, "groups", items, state, until)


@router.get("/v1.0/groups/{gid}")
def read_group(request: Request, gid: str):
    store = store_of(request)
    require(request, ("Group.Read.All", "GroupMember.Read.All"))
    fields = parse_select(request, GROUP_FIELDS, "microsoft.graph.group") or sorted(GROUP_FIELDS)
    return {"@odata.context": f"{GRAPH_ROOT}/$metadata#groups/$entity", **project(get_group(store, gid), fields)}


@router.get("/v1.0/groups/{gid}/members")
def group_members(request: Request, gid: str):
    store = store_of(request)
    require(request, ("Group.Read.All", "GroupMember.Read.All"))
    get_group(store, gid)
    items = [r for r in (member_ref(store, m) for m in store.members[gid]) if r]
    return paged(request, "directoryObjects", items, page_size(request, 100, 999))


@router.get("/v1.0/groups/{gid}/transitiveMembers")
def group_transitive_members(request: Request, gid: str):
    store = store_of(request)
    require(request, ("Group.Read.All", "GroupMember.Read.All"))
    get_group(store, gid)
    items = [member_ref(store, m) for m in transitive(store, gid)]
    return paged(request, "directoryObjects", items, page_size(request, 100, 999))


@router.post("/v1.0/groups/{gid}/members/$ref")
async def add_member(request: Request, gid: str):
    store = store_of(request)
    require(request, ("GroupMember.ReadWrite.All", "Group.ReadWrite.All"))
    get_group(store, gid)
    ref = (await request.json()).get("@odata.id", "")
    mid = ref.rstrip("/").rsplit("/", 1)[-1]
    if member_ref(store, mid) is None:
        raise GraphError(404, "Request_ResourceNotFound", f"Resource '{mid}' does not exist or one of its queried reference-property objects are not present.")
    if mid in store.members[gid]:
        raise GraphError(400, "Request_BadRequest",
                         "One or more added object references already exist for the following modified properties: 'members'.")
    if gate(store, gid):
        store.members[gid].append(mid)
        store.member_log.append((store.bump(), gid, mid, False))
    return Response(status_code=204)


@router.delete("/v1.0/groups/{gid}/members/{mid}/$ref")
def remove_member(request: Request, gid: str, mid: str):
    store = store_of(request)
    require(request, ("GroupMember.ReadWrite.All", "Group.ReadWrite.All"))
    get_group(store, gid)
    if mid not in store.members[gid]:
        raise GraphError(404, "Request_ResourceNotFound", f"Resource '{mid}' does not exist or one of its queried reference-property objects are not present.")
    if gate(store, gid):
        store.members[gid].remove(mid)
        store.member_log.append((store.bump(), gid, mid, True))
    return Response(status_code=204)


# ---------- 目錄角色 ----------

@router.get("/v1.0/roleManagement/directory/roleDefinitions")
def role_definitions(request: Request):
    store = store_of(request)
    require(request, ("RoleManagement.Read.Directory", "RoleManagement.ReadWrite.Directory"))
    return {"@odata.context": f"{GRAPH_ROOT}/$metadata#roleManagement/directory/roleDefinitions", "value": store.role_defs}


@router.get("/v1.0/roleManagement/directory/roleAssignments")
def role_assignments(request: Request):
    store = store_of(request)
    require(request, ("RoleManagement.Read.Directory", "RoleManagement.ReadWrite.Directory"))
    items = list(store.role_assignments.values())
    flt = request.query_params.get("$filter")
    if flt:
        m = re.fullmatch(r"principalId eq '([0-9a-f-]+)'", flt.strip())
        if not m:
            raise GraphError(400, "Request_UnsupportedQuery", "Unsupported or invalid query filter clause specified.")
        items = [a for a in items if a["principalId"] == m.group(1)]
    return paged(request, "roleManagement/directory/roleAssignments", items, page_size(request, 100, 999))


@router.post("/v1.0/roleManagement/directory/roleAssignments")
async def create_role_assignment(request: Request):
    store = store_of(request)
    require(request, "RoleManagement.ReadWrite.Directory")
    body = await request.json()
    if body.get("principalId") not in store.users or body.get("roleDefinitionId") not in {d["id"] for d in store.role_defs}:
        raise GraphError(400, "Request_BadRequest", "Invalid principalId or roleDefinitionId.")
    a = {"id": str(uuid.uuid4()), "principalId": body["principalId"], "roleDefinitionId": body["roleDefinitionId"],
         "directoryScopeId": body.get("directoryScopeId", "/")}
    if gate(store, body["principalId"]):
        store.role_assignments[a["id"]] = a
    return JSONResponse({"@odata.context": f"{GRAPH_ROOT}/$metadata#roleManagement/directory/roleAssignments/$entity", **a}, 201)


@router.delete("/v1.0/roleManagement/directory/roleAssignments/{aid}")
def delete_role_assignment(request: Request, aid: str):
    store = store_of(request)
    require(request, "RoleManagement.ReadWrite.Directory")
    if aid not in store.role_assignments:
        raise GraphError(404, "Request_ResourceNotFound", f"Resource '{aid}' does not exist.")
    if gate(store, aid):
        store.role_assignments.pop(aid)
    return Response(status_code=204)


# ---------- 已刪除項目（還原用） ----------

@router.get("/v1.0/directory/deletedItems/microsoft.graph.user")
def deleted_users(request: Request):
    store = store_of(request)
    require(request, "User.Read.All")
    items = [project(u, USER_DEFAULT + ["deletedDateTime"]) for u in store.deleted_users.values()]
    return paged(request, "directoryObjects", items, page_size(request, 100, 999))


@router.post("/v1.0/directory/deletedItems/{oid}/restore")
def restore_user(request: Request, oid: str):
    store = store_of(request)
    require(request, ("User.DeleteRestore.All", "User.ReadWrite.All"))
    if oid not in store.deleted_users:
        raise GraphError(404, "Request_ResourceNotFound", f"Resource '{oid}' does not exist.")
    if gate(store, oid):
        u = store.deleted_users.pop(oid)
        u.pop("deletedDateTime", None)
        store.users[oid] = u
        store.user_log.append((store.bump(), oid))
    return {"@odata.context": f"{GRAPH_ROOT}/$metadata#directoryObjects/$entity", **project(store.users.get(oid) or
                                                                                            store.deleted_users[oid], USER_DEFAULT)}
