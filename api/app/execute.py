"""執行引擎：把發現變成動作，經人核准後執行、驗證，必要時還原。

流程：plan（從發現產生動作）→ approve（人核准，綁定動作內容的指紋）→ run → rollback

run 對每個動作：
1. 指紋必須和核准時一致，否則拒絕（防止核准後動作內容被改）
2. 保護清單在執行當下再檢查一次（不只在產生計畫時）
3. 用唯讀 key 讀現況，第一次讀到的狀態存成「執行前狀態」，還原時以它為準
4. 已經是目標狀態就不寫（冪等）；否則用寫入 key 執行
5. 再用唯讀 key 重新讀一次：寫入回成功不代表真的生效，讀不到變化就標成驗證失敗

每做完一步就把帳本存檔。中途中斷後重跑：已驗證的跳過，執行到一半的先讀現況再決定，不會重複動作。

python -m app.execute plan | approve --all --by 姓名 [--ack-irreversible] | run [--confirm-large] | status | rollback --ids ...
"""

import argparse
import hashlib
import json
import os
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote

import httpx

from app.connectors.github import GitHubClient
from app.connectors.graph import GraphApp, GraphClient
from app.findings import POLICY, Finding

# 數字是執行順序：先拿掉管理員角色，否則有角色的帳號無法被停用
EXECUTABLE = {"remove_role_assignment": 0, "remove_group_member": 1, "remove_guest": 2, "disable_account": 3,
              "remove_github_member": 4, "remove_outside_collaborator": 4}
IRREVERSIBLE = {"remove_github_member": "重新加入只會送出邀請，對方接受前沒有權限，私人 fork 也會被移除",
                "remove_outside_collaborator": "還原要重新逐一加回各 repo 的權限"}
MANUAL = {"remove_erp_role": "ERP 沒有開放 API：開工單給 ERP 管理員移除角色",
          "require_2fa": "通知本人限期開啟 2FA，逾期再移除",
          "confirm_identity": "請帳號持有人認領，或由 IT 確認是誰的帳號後再決定",
          "review_groups": "交給主管逐一覆核"}
DONE = {"verified", "rolled_back", "rolled_back_partial"}


class BatchTooLarge(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


@dataclass
class Action:
    id: str
    fix: str
    system: str
    account: str
    object: str
    rule: str
    target: dict
    irreversible: bool
    status: str = "planned"
    approval: dict | None = None
    before: dict | None = None
    result: dict | None = None
    history: list = field(default_factory=list)

    def fingerprint(self) -> str:
        body = json.dumps([self.fix, self.system, self.account, self.object, self.target], sort_keys=True)
        return hashlib.sha256(body.encode()).hexdigest()

    def log(self, event: str, **detail):
        self.history.append({"at": now(), "event": event, **detail})


def plan(findings: list[Finding], snapshot: dict) -> dict:
    users = {u["userPrincipalName"]: u["id"] for u in snapshot["entra"]["users"]}
    groups = {g["displayName"]: g["id"] for g in snapshot["entra"]["groups"]}
    roles = {a["id"]: a["roleDefinitionId"] for a in snapshot["entra"]["roleAssignments"]}
    actions, manual = {}, []
    for f in findings:
        if f.fix in MANUAL or not f.confirmed:
            manual.append({"rule": f.rule, "account": f.account, "object": f.object, "fix": f.fix,
                           "how": MANUAL.get(f.fix, "身分只是候選對應，先確認再處理")})
            continue
        if f.fix in ("remove_github_member", "remove_outside_collaborator"):
            target = {"login": f.account}
        else:
            target = {"user_id": users[f.account]}
            if f.fix == "remove_group_member":
                target["group_id"] = groups[f.object]
            if f.fix == "remove_role_assignment":
                target["role_definition_id"] = roles[f.evidence["assignment_id"]]
        aid = hashlib.sha1(json.dumps([f.fix, f.account, f.object]).encode()).hexdigest()[:12]
        actions[aid] = Action(aid, f.fix, f.system, f.account, f.object, f.rule, target, f.fix in IRREVERSIBLE)
    ordered = sorted(actions.values(), key=lambda a: (EXECUTABLE[a.fix], a.account, a.object))
    return {"id": datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ"), "created_at": now(),
            "actions": [asdict(a) for a in ordered], "manual": manual}


class Ledger:
    def __init__(self, path: Path):
        self.path = path
        data = json.loads(path.read_text())
        self.meta = {k: v for k, v in data.items() if k != "actions"}
        self.actions = {a["id"]: Action(**a) for a in data["actions"]}

    @classmethod
    def create(cls, path: Path, plan_data: dict) -> "Ledger":
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(plan_data, ensure_ascii=False, indent=1))
        return cls(path)

    def save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.meta | {"actions": [asdict(a) for a in self.actions.values()]},
                                  ensure_ascii=False, indent=1))
        tmp.replace(self.path)  # 原子替換：存到一半斷電也不會留下壞掉的帳本


class Executor:
    def __init__(self, ledger: Ledger, writer: GraphClient, reader: GraphClient, gh_admin: GitHubClient,
                 gh_reader: GitHubClient, policy: dict = POLICY, after_write=None):
        self.ledger, self.writer, self.reader = ledger, writer, reader
        self.gh_admin, self.gh_reader, self.policy = gh_admin, gh_reader, policy
        self.after_write = after_write or (lambda a: None)

    # ---------- 核准 ----------
    def approve(self, ids: list[str] | None, by: str, ack_irreversible: bool = False) -> list[str]:
        done = []
        for a in self.ledger.actions.values():
            if (ids is not None and a.id not in ids) or a.status != "planned":
                continue
            if a.irreversible and not ack_irreversible:
                a.log("approval_skipped", reason=f"不可逆動作需要特別確認：{IRREVERSIBLE[a.fix]}")
                continue
            a.approval = {"by": by, "at": now(), "fingerprint": a.fingerprint()}
            a.status = "approved"
            a.log("approved", by=by)
            done.append(a.id)
        self.ledger.save()
        return done

    # ---------- 讀現況（一律用唯讀 key） ----------
    def read(self, a: Action) -> dict:
        t = a.target
        if a.fix == "remove_github_member":
            r = self.gh_reader.call("GET", f"/orgs/{self.gh_reader.org}/memberships/{t['login']}")
            body = r.json() if r.status_code == 200 else {}
            return {"present": body.get("state") == "active", "role": body.get("role")}
        if a.fix == "remove_outside_collaborator":
            return {"present": t["login"] in {m["login"] for m in self.gh_reader.outside_collaborators()}}
        if a.fix == "remove_role_assignment":
            found = [x for x in self.reader.pages(
                f"/v1.0/roleManagement/directory/roleAssignments?$filter=principalId eq '{t['user_id']}'")
                     if x["roleDefinitionId"] == t["role_definition_id"]]
            return {"present": bool(found), "assignment_ids": [x["id"] for x in found]}
        if a.fix == "remove_group_member":
            groups = {g["id"] for g in self.reader.pages(f"/v1.0/users/{t['user_id']}/memberOf")}
            return {"present": t["group_id"] in groups}
        r = self.reader.call("GET", f"/v1.0/users/{t['user_id']}?$select=id,userPrincipalName,accountEnabled")
        if a.fix == "remove_guest":
            return {"present": r.status_code == 200}
        return {"present": r.json()["accountEnabled"]}

    def has_roles(self, uid: str) -> bool:
        return bool(self.reader.pages(f"/v1.0/roleManagement/directory/roleAssignments?$filter=principalId eq '{uid}'"))

    # ---------- 寫（寫入 key） ----------
    def write(self, a: Action, state: dict) -> httpx.Response:
        t = a.target
        if a.fix == "disable_account":
            r = self.writer.call("PATCH", f"/v1.0/users/{t['user_id']}", json={"accountEnabled": False})
            if r.status_code == 204:
                a.log("sessions_revoked", ok=self.writer.call(
                    "POST", f"/v1.0/users/{t['user_id']}/revokeSignInSessions").status_code == 200)
            return r
        if a.fix == "remove_group_member":
            return self.writer.call("DELETE", f"/v1.0/groups/{t['group_id']}/members/{t['user_id']}/$ref")
        if a.fix == "remove_role_assignment":
            r = None
            for aid in state["assignment_ids"]:
                r = self.writer.call("DELETE", f"/v1.0/roleManagement/directory/roleAssignments/{aid}")
                if r.status_code not in (204, 404):
                    return r
            return r
        if a.fix == "remove_guest":
            return self.writer.call("DELETE", f"/v1.0/users/{t['user_id']}")
        kind = "members" if a.fix == "remove_github_member" else "outside_collaborators"
        return self.gh_admin.call("DELETE", f"/orgs/{self.gh_admin.org}/{kind}/{quote(t['login'])}")

    def protected(self, a: Action) -> bool:
        local = a.account.split("@")[0].lower()
        return local in {p.lower() for p in self.policy["protected_accounts"]}

    # ---------- 執行 ----------
    def run(self, confirm_large: bool = False) -> dict:
        todo = [a for a in self.ledger.actions.values() if a.status in ("approved", "executing", "applied")]
        limit = self.policy["max_batch_actions"]
        if len(todo) > limit and not confirm_large:
            raise BatchTooLarge(f"這次要執行 {len(todo)} 筆，超過上限 {limit} 筆，請確認後加上 --confirm-large")
        for a in sorted(todo, key=lambda a: EXECUTABLE[a.fix]):
            self.run_one(a)
            self.ledger.save()
        return dict(Counter(a.status for a in self.ledger.actions.values()))

    def run_one(self, a: Action):
        if a.approval is None or a.approval["fingerprint"] != a.fingerprint():
            a.status = "refused"
            a.log("refused", reason="動作內容和核准時不一致")
            return
        if self.protected(a):
            a.status = "blocked"
            a.log("blocked", reason="保護清單內的帳號")
            return
        if a.status in ("approved", "executing"):
            state = self.read(a)
            if a.before is None:
                a.before = state
            if not state["present"]:
                a.status, a.result = "applied", {"noop": True}
                a.log("already_applied")
            elif a.fix == "disable_account" and self.has_roles(a.target["user_id"]):
                a.status = "blocked"
                a.log("blocked", reason="帳號擔任管理員角色，必須先移除角色才能停用")
                return
            else:
                a.status = "executing"
                a.log("executing")
                self.ledger.save()
                r = self.write(a, state)
                self.after_write(a)
                if r.status_code in (200, 204, 404):  # 404：已經不在了，視為完成
                    a.status, a.result = "applied", {"http": r.status_code}
                    a.log("applied", http=r.status_code)
                else:
                    a.status, a.result = "failed", {"http": r.status_code, "body": r.text[:300]}
                    a.log("failed", http=r.status_code)
                    return
        after = self.read(a)
        if after["present"]:
            a.status = "verify_failed"
            a.log("verify_failed", reason="寫入回報成功，但重新讀取後存取權仍在")
        else:
            a.status = "verified"
            a.log("verified")

    # ---------- 還原 ----------
    def rollback(self, ids: list[str], by: str) -> dict:
        for a in self.ledger.actions.values():
            if a.id in ids and a.status in ("verified", "verify_failed", "applied"):
                self.rollback_one(a, by)
                self.ledger.save()
        return dict(Counter(a.status for a in self.ledger.actions.values() if a.id in ids))

    def rollback_one(self, a: Action, by: str):
        t = a.target
        if not a.before["present"]:
            a.status = "rolled_back"
            a.log("rolled_back", by=by, note="執行前就已是目標狀態，沒有需要還原的")
            return
        if a.fix == "disable_account":
            self.writer.call("PATCH", f"/v1.0/users/{t['user_id']}", json={"accountEnabled": True})
        elif a.fix == "remove_group_member":
            self.writer.call("POST", f"/v1.0/groups/{t['group_id']}/members/$ref",
                             json={"@odata.id": f"https://graph.microsoft.com/v1.0/directoryObjects/{t['user_id']}"})
        elif a.fix == "remove_role_assignment":
            if not self.read(a)["present"]:
                self.writer.call("POST", "/v1.0/roleManagement/directory/roleAssignments", json={
                    "principalId": t["user_id"], "roleDefinitionId": t["role_definition_id"], "directoryScopeId": "/"})
        elif a.fix == "remove_guest":
            self.writer.call("POST", f"/v1.0/directory/deletedItems/{t['user_id']}/restore")
        elif a.fix == "remove_github_member":
            self.gh_admin.call("PUT", f"/orgs/{self.gh_admin.org}/memberships/{quote(t['login'])}",
                               json={"role": a.before.get("role") or "member"})
            a.status = "rolled_back_partial"
            a.log("rolled_back_partial", by=by, note="已重新邀請，對方接受前不會恢復權限")
            return
        else:
            a.status = "rollback_unsupported"
            a.log("rollback_unsupported", by=by, note=IRREVERSIBLE[a.fix])
            return
        if self.read(a)["present"]:
            a.status = "rolled_back"
            a.log("rolled_back", by=by)
        else:
            a.status = "rollback_failed"
            a.log("rollback_failed", by=by)


# ---------- CLI ----------

def clients(http: httpx.Client) -> tuple[GraphClient, GraphClient, GitHubClient, GitHubClient]:
    from app.sync import clients_from_env
    env = os.environ
    reader, gh_reader = clients_from_env(http)
    if env.get("KEYWARD_SOURCE", "mock") == "mock":
        base = env.get("MOCK_URL", f"http://127.0.0.1:{env.get('MOCK_PORT', '8391')}")
        writer = GraphClient(http, GraphApp("arcwell", env["MOCK_GRAPH_WRITER_ID"], env["MOCK_GRAPH_WRITER_SECRET"]),
                             base, f"{base}/login")
        gh_admin = GitHubClient(http, f"{base}/github", gh_reader.org, env["MOCK_GITHUB_ADMIN_TOKEN"])
    else:
        writer = GraphClient(http, GraphApp(env["ENTRA_TENANT_ID"], env["ENTRA_WRITER_CLIENT_ID"],
                                            env["ENTRA_WRITER_CLIENT_SECRET"]),
                             "https://graph.microsoft.com", "https://login.microsoftonline.com")
        gh_admin = GitHubClient(http, "https://api.github.com", gh_reader.org, env["GITHUB_ADMIN_TOKEN"])
    return writer, reader, gh_admin, gh_reader


def main():
    from app.sync import DATA
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["plan", "approve", "run", "status", "rollback"])
    ap.add_argument("--ledger", type=Path)
    ap.add_argument("--ids", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--by")
    ap.add_argument("--ack-irreversible", action="store_true")
    ap.add_argument("--confirm-large", action="store_true")
    args = ap.parse_args()
    exec_dir = DATA / "state" / "executions"

    if args.command == "plan":
        findings = [Finding(**f) for f in json.loads((DATA / "state" / "findings.json").read_text())]
        snap = json.loads(max((DATA / "state" / "snapshots").glob("*.json")).read_text())
        p = plan(findings, snap)
        ledger = Ledger.create(exec_dir / f"{p['id']}.json", p)
        print(json.dumps({"ledger": str(ledger.path), "actions": Counter(a.fix for a in ledger.actions.values()),
                          "manual": Counter(m["fix"] for m in p["manual"])}, ensure_ascii=False))
        return

    ledger = Ledger(args.ledger or max(exec_dir.glob("*.json")))
    if args.command == "status":
        print(json.dumps({"ledger": str(ledger.path), "status": Counter(a.status for a in ledger.actions.values())},
                         ensure_ascii=False))
        return
    with httpx.Client(timeout=30) as http:
        ex = Executor(ledger, *clients(http))
        if args.command == "approve":
            if not args.by or not (args.all or args.ids):
                ap.error("approve 需要 --by 與 --all 或 --ids")
            ids = None if args.all else args.ids
            print(json.dumps({"approved": len(ex.approve(ids, args.by, args.ack_irreversible))}))
        elif args.command == "run":
            try:
                print(json.dumps(ex.run(args.confirm_large), ensure_ascii=False))
            except BatchTooLarge as e:
                raise SystemExit(str(e))
        else:
            if not args.by or not args.ids:
                ap.error("rollback 需要 --by 與 --ids")
            print(json.dumps(ex.rollback(args.ids, args.by), ensure_ascii=False))


if __name__ == "__main__":
    main()
