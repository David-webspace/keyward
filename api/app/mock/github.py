"""GitHub REST API 的 mock（organization 成員相關端點）。

分頁用 Link header；權限比照 fine-grained token 的 Members 讀／寫。移除成員後無法真正還原：
重新加入只會送出邀請，對方接受前都是 pending，這點和真實 GitHub 一致。
"""

import secrets

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse, Response

from app.mock.state import Store, WriteFailed

DOCS = "https://docs.github.com/rest"


class GitHubError(Exception):
    def __init__(self, status: int, message: str, headers: dict | None = None):
        self.status, self.message, self.headers = status, message, headers


def store_of(request: Request) -> Store:
    return request.app.state.store


def require(request: Request, write: bool = False):
    auth = request.headers.get("authorization", "")
    tok = auth.split(" ", 1)[1].strip() if " " in auth else ""
    tokens = request.app.state.github_tokens
    level = next((lvl for lvl, t in tokens.items() if tok and secrets.compare_digest(t, tok)), None)
    if level is None:
        raise GitHubError(401, "Bad credentials")
    if write and level != "admin":
        raise GitHubError(403, "Resource not accessible by personal access token")


def check_org(store: Store, org: str):
    if org.lower() != store.gh_org.lower():
        raise GitHubError(404, "Not Found")


def simple(u: dict) -> dict:
    return {"login": u["login"], "id": u["id"], "node_id": f"U_{u['id']}", "type": u["type"], "site_admin": u["site_admin"],
            "url": f"https://api.github.com/users/{u['login']}"}


def paginate(request: Request, items: list) -> JSONResponse:
    per_page = min(int(request.query_params.get("per_page", 30)), 100)
    page = max(int(request.query_params.get("page", 1)), 1)
    chunk = items[(page - 1) * per_page: page * per_page]
    last = max(1, -(-len(items) // per_page))
    links = []
    if page < last:
        links.append(f'<{request.url.include_query_params(page=page + 1, per_page=per_page)}>; rel="next"')
        links.append(f'<{request.url.include_query_params(page=last, per_page=per_page)}>; rel="last"')
    if page > 1:
        links.append(f'<{request.url.include_query_params(page=1, per_page=per_page)}>; rel="first"')
        links.append(f'<{request.url.include_query_params(page=page - 1, per_page=per_page)}>; rel="prev"')
    return JSONResponse(chunk, headers={"Link": ", ".join(links)} if links else {})


def gate(store: Store, target: str) -> bool:
    try:
        return store.write_gate(target)
    except WriteFailed:
        raise GitHubError(503, "Service Unavailable")


router = APIRouter(prefix="/github")


@router.get("/orgs/{org}/members")
def members(request: Request, org: str):
    store = store_of(request)
    require(request)
    check_org(store, org)
    items = list(store.gh_members.values())
    if request.query_params.get("filter") == "2fa_disabled":
        items = [m for m in items if not m["two_factor"]]
    role = request.query_params.get("role", "all")
    if role != "all":
        items = [m for m in items if m["role"] == role]
    return paginate(request, [simple(m) for m in items])


@router.get("/orgs/{org}/members/{login}")
def is_member(request: Request, org: str, login: str):
    store = store_of(request)
    require(request)
    check_org(store, org)
    return Response(status_code=204 if login in store.gh_members else 404)


@router.get("/orgs/{org}/memberships/{login}")
def membership(request: Request, org: str, login: str):
    store = store_of(request)
    require(request)
    check_org(store, org)
    if login in store.gh_members:
        m = store.gh_members[login]
        return {"state": "active", "role": m["role"], "user": simple(m)}
    if login in store.gh_invitations:
        return store.gh_invitations[login]
    raise GitHubError(404, "Not Found")


@router.put("/orgs/{org}/memberships/{login}")
async def set_membership(request: Request, org: str, login: str):
    store = store_of(request)
    require(request, write=True)
    check_org(store, org)
    role = (await request.json()).get("role", "member")
    if login in store.gh_members:
        if gate(store, login):
            store.gh_members[login]["role"] = "admin" if role == "admin" else "member"
        m = store.gh_members[login]
        return {"state": "active", "role": m["role"], "user": simple(m)}
    if gate(store, login):
        store.gh_invitations[login] = {"state": "pending", "role": role, "user": {"login": login}}
    return store.gh_invitations.get(login, {"state": "pending", "role": role, "user": {"login": login}})


@router.delete("/orgs/{org}/members/{login}")
def remove_member(request: Request, org: str, login: str):
    store = store_of(request)
    require(request, write=True)
    check_org(store, org)
    if login not in store.gh_members:
        raise GitHubError(404, "Not Found")
    if gate(store, login):
        store.gh_members.pop(login)
        for ms in store.gh_team_members.values():
            if login in ms:
                ms.remove(login)
    return Response(status_code=204)


@router.get("/orgs/{org}/outside_collaborators")
def outside(request: Request, org: str):
    store = store_of(request)
    require(request)
    check_org(store, org)
    return paginate(request, [simple(m) for m in store.gh_outside.values()])


@router.delete("/orgs/{org}/outside_collaborators/{login}")
def remove_outside(request: Request, org: str, login: str):
    store = store_of(request)
    require(request, write=True)
    check_org(store, org)
    if login not in store.gh_outside:
        raise GitHubError(404, "Not Found")
    if gate(store, login):
        store.gh_outside.pop(login)
    return Response(status_code=204)


@router.get("/orgs/{org}/teams")
def teams(request: Request, org: str):
    store = store_of(request)
    require(request)
    check_org(store, org)
    return paginate(request, list(store.gh_teams.values()))


@router.get("/orgs/{org}/teams/{slug}/members")
def team_members(request: Request, org: str, slug: str):
    store = store_of(request)
    require(request)
    check_org(store, org)
    if slug not in store.gh_teams:
        raise GitHubError(404, "Not Found")
    return paginate(request, [simple(store.gh_members[x]) for x in store.gh_team_members[slug] if x in store.gh_members])


@router.get("/users/{login}")
def user(request: Request, login: str):
    store = store_of(request)
    require(request)
    u = store.gh_members.get(login) or store.gh_outside.get(login)
    if u is None:
        raise GitHubError(404, "Not Found")
    return {**simple(u), "name": u["name"], "email": u["email"], "company": u["company"], "created_at": u["created_at"]}
