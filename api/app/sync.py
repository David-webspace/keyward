"""同步：把 Entra 與 GitHub 的現況拉下來，存成一份快照。

- Entra 使用者與群組用 delta query：第一次全量，之後只拉變動（deltaLink 存在 state 檔）。
- signInActivity 不支援 delta，每次另外全量讀（每頁 120 筆）；租戶沒有 P1/P2 時記為無法取得。
- 目錄角色、GitHub 數量小，每次全量。GitHub 個人資料（姓名、公開 Email）有快取，只查新出現的帳號。

python -m app.sync            # 增量（沒有 state 檔就是全量）
python -m app.sync --full     # 丟掉 deltaLink 重新全量
"""

import argparse
import json
import os
from datetime import datetime, timezone
from pathlib import Path

import httpx

from app.connectors.github import GitHubClient
from app.connectors.graph import GraphApp, GraphClient

ROOT = Path(__file__).resolve().parents[2]
DATA = Path(os.environ.get("DATA_DIR", ROOT / "data"))


def empty_state() -> dict:
    return {"users_delta": None, "groups_delta": None, "users": {}, "groups": {}, "members": {}, "gh_profiles": {}}


def apply_users(state: dict, items: list[dict]) -> int:
    for it in items:
        if "@removed" in it:
            state["users"].pop(it["id"], None)
        else:
            state["users"].setdefault(it["id"], {}).update(it)
    return len(items)


def apply_groups(state: dict, items: list[dict]) -> int:
    changes = 0
    for g in items:
        gid = g["id"]
        if "@removed" in g:
            state["groups"].pop(gid, None)
            state["members"].pop(gid, None)
            continue
        props = {k: v for k, v in g.items() if k != "members@delta"}
        state["groups"].setdefault(gid, {}).update(props)
        ms = state["members"].setdefault(gid, {})
        for m in g.get("members@delta", []):
            changes += 1
            if "@removed" in m:
                ms.pop(m["id"], None)
            else:
                ms[m["id"]] = "group" if m["@odata.type"].endswith("group") else "user"
    return changes


def sync(graph: GraphClient, github: GitHubClient, state: dict) -> dict:
    full = state["users_delta"] is None
    users, state["users_delta"] = graph.users_delta(state["users_delta"])
    groups, state["groups_delta"] = graph.groups_delta(state["groups_delta"])
    stats = {"user_changes": apply_users(state, users), "membership_changes": apply_groups(state, groups)}
    sign_in = graph.sign_in_activity()

    members = github.members()
    no_2fa, admins = github.without_2fa(), github.admins()
    outside = github.outside_collaborators()
    for m in members + outside:
        if m["login"] not in state["gh_profiles"]:
            p = github.profile(m["login"])
            state["gh_profiles"][m["login"]] = {"name": p.get("name"), "email": p.get("email")}

    def gh(m: dict, **extra) -> dict:
        return {"login": m["login"], "id": m["id"], **state["gh_profiles"][m["login"]], **extra}

    stats.update(graph_retries=graph.rt.retries, github_retries=github.rt.retries)
    return {
        "taken_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "mode": "full" if full else "incremental",
        "entra": {
            "users": [u | ({"signInActivity": sign_in.get(uid)} if sign_in is not None else {})
                      for uid, u in state["users"].items()],
            "sign_in_available": sign_in is not None,
            "groups": list(state["groups"].values()),
            "members": {gid: [{"id": mid, "type": t} for mid, t in ms.items()] for gid, ms in state["members"].items()},
            "roleDefinitions": graph.role_definitions(),
            "roleAssignments": graph.role_assignments(),
        },
        "github": {
            "org": github.org,
            "members": [gh(m, role="admin" if m["login"] in admins else "member", two_factor=m["login"] not in no_2fa)
                        for m in members],
            "outside_collaborators": [gh(m) for m in outside],
        },
        "stats": stats,
    }


def run(graph: GraphClient, github: GitHubClient, state_dir: Path, full: bool = False) -> tuple[dict, Path]:
    state_dir.mkdir(parents=True, exist_ok=True)
    state_file = state_dir / "sync_state.json"
    state = empty_state() if full or not state_file.exists() else json.loads(state_file.read_text())
    snap = sync(graph, github, state)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")  # 帶微秒：同一秒內連跑兩次也不會互相覆蓋
    snap_dir = state_dir / "snapshots"
    snap_dir.mkdir(exist_ok=True)
    path = snap_dir / f"{stamp}.json"
    path.write_text(json.dumps(snap, ensure_ascii=False))
    state_file.write_text(json.dumps(state, ensure_ascii=False))
    return snap, path


def clients_from_env(http: httpx.Client) -> tuple[GraphClient, GitHubClient]:
    """KEYWARD_SOURCE=mock 時連本機 mock；live 時連真實租戶與 GitHub。"""
    env = os.environ
    if env.get("KEYWARD_SOURCE", "mock") == "mock":
        base = env.get("MOCK_URL", f"http://127.0.0.1:{env.get('MOCK_PORT', '8391')}")
        app = GraphApp("arcwell", env["MOCK_GRAPH_READER_ID"], env["MOCK_GRAPH_READER_SECRET"])
        return (GraphClient(http, app, base, f"{base}/login"),
                GitHubClient(http, f"{base}/github", "arcwell-demo", env["MOCK_GITHUB_READ_TOKEN"]))
    app = GraphApp(env["ENTRA_TENANT_ID"], env["ENTRA_READER_CLIENT_ID"], env["ENTRA_READER_CLIENT_SECRET"])
    return (GraphClient(http, app, "https://graph.microsoft.com", "https://login.microsoftonline.com"),
            GitHubClient(http, "https://api.github.com", env["GITHUB_ORG"], env["GITHUB_READ_TOKEN"]))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true")
    args = ap.parse_args()
    with httpx.Client(timeout=30) as http:
        graph, github = clients_from_env(http)
        snap, path = run(graph, github, DATA / "state", full=args.full)
    print(json.dumps({"snapshot": str(path), "mode": snap["mode"], **snap["stats"]}, ensure_ascii=False))


if __name__ == "__main__":
    main()
