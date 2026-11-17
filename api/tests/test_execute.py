"""執行引擎：核准、冪等、驗證、還原、保護清單，以及各種故障下的行為。"""

import json
from collections import Counter
from dataclasses import asdict
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.connectors.github import GitHubClient
from app.connectors.graph import GraphApp, GraphClient
from app.execute import Action, BatchTooLarge, Executor, Ledger, plan
from app.findings import evaluate
from app.internal import load
from app.mock.main import create_app
from app.sync import empty_state, sync
from tests.conftest import ENV

NO_SLEEP = {"sleep": lambda _: None}


class Env:
    def __init__(self, http, world_dir, tmp_path, truth):
        self.http, self.world_dir, self.tmp_path = http, world_dir, tmp_path
        base = "http://testserver"
        self.reader = GraphClient(http, GraphApp("t", ENV["MOCK_GRAPH_READER_ID"], ENV["MOCK_GRAPH_READER_SECRET"]),
                                  base, f"{base}/login", **NO_SLEEP)
        self.writer = GraphClient(http, GraphApp("t", ENV["MOCK_GRAPH_WRITER_ID"], ENV["MOCK_GRAPH_WRITER_SECRET"]),
                                  base, f"{base}/login", **NO_SLEEP)
        self.gh_reader = GitHubClient(http, f"{base}/github", "arcwell-demo", ENV["MOCK_GITHUB_READ_TOKEN"], **NO_SLEEP)
        self.gh_admin = GitHubClient(http, f"{base}/github", "arcwell-demo", ENV["MOCK_GITHUB_ADMIN_TOKEN"], **NO_SLEEP)
        self.internal = load(world_dir)
        self.as_of = date.fromisoformat(truth["as_of"])
        self.state = empty_state()
        self.snapshot = sync(self.reader, self.gh_reader, self.state)
        self.findings = evaluate(self.snapshot, self.internal, self.as_of)

    def ledger(self, only=None, name="ledger.json") -> Ledger:
        p = plan(self.findings, self.snapshot)
        if only:
            p["actions"] = [a for a in p["actions"] if only(a)]
        return Ledger.create(self.tmp_path / name, p)

    def executor(self, ledger, **kw) -> Executor:
        return Executor(ledger, self.writer, self.reader, self.gh_admin, self.gh_reader, **kw)

    def stats(self) -> dict:
        return self.http.get("/_mock/stats").json()

    def faults(self, **f):
        self.http.put("/_mock/faults", json=f)

    def resync(self):
        return evaluate(sync(self.reader, self.gh_reader, self.state), self.internal, self.as_of)


@pytest.fixture
def env(world_dir, tmp_path, truth):
    with TestClient(create_app(world_dir, ENV)) as http:
        yield Env(http, world_dir, tmp_path, truth)


def sample(ledger: Ledger, per_fix: int = 1) -> list[str]:
    picked, seen = [], Counter()
    for a in ledger.actions.values():
        if seen[a.fix] < per_fix:
            picked.append(a.id)
            seen[a.fix] += 1
    return picked


def test_plan_splits_automatic_and_manual(env):
    p = plan(env.findings, env.snapshot)
    auto = Counter(a["fix"] for a in p["actions"])
    manual = Counter(m["fix"] for m in p["manual"])
    assert auto == {"disable_account": 39, "remove_group_member": 48, "remove_guest": 15,
                    "remove_role_assignment": 5, "remove_github_member": 6, "remove_outside_collaborator": 2}
    assert manual == {"remove_erp_role": 12, "require_2fa": 7, "confirm_identity": 13, "review_groups": 15}
    order = [a["fix"] for a in p["actions"]]
    assert order.index("remove_role_assignment") < order.index("disable_account")


def test_nothing_runs_without_approval(env):
    ex = env.executor(env.ledger())
    ex.run(confirm_large=True)
    assert env.stats()["writes"] == 0


def test_irreversible_needs_explicit_ack(env):
    ledger = env.ledger(lambda a: a["irreversible"])
    ex = env.executor(ledger)
    assert ex.approve(None, "it.lead") == []
    assert len(ex.approve(None, "it.lead", ack_irreversible=True)) == 8


def test_large_batch_is_refused_before_any_write(env):
    ex = env.executor(env.ledger())
    ex.approve(None, "it.lead", ack_irreversible=True)
    with pytest.raises(BatchTooLarge):
        ex.run()
    assert env.stats()["writes"] == 0


def test_full_run_verifies_everything_and_findings_clear(env):
    ledger = env.ledger()
    ex = env.executor(ledger)
    ex.approve(None, "it.lead", ack_irreversible=True)
    assert ex.run(confirm_large=True) == {"verified": len(ledger.actions)}
    writes = env.stats()["writes"]
    remaining = Counter(f.fix for f in env.resync())
    assert set(remaining) == {"remove_erp_role", "require_2fa", "confirm_identity", "review_groups"}
    ex.run(confirm_large=True)  # 再跑一次：全部已驗證，不應再寫
    assert env.stats()["writes"] == writes


def test_transient_failures_are_retried_without_duplicates(env):
    ledger = env.ledger()
    ex = env.executor(ledger)
    ex.approve(None, "it.lead", ack_irreversible=True)
    env.faults(fail_writes=[3, 17, 40], throttle_every=9)
    assert ex.run(confirm_large=True) == {"verified": len(ledger.actions)}
    s = env.stats()
    assert s["writes"] - s["applied_writes"] == 3  # 只有注入的 3 次失敗沒生效，其餘每次寫入都剛好一次


def test_silent_failure_is_caught_by_verification(env, truth, entra):
    upn = next(i["account"] for i in truth["issues"] if i["type"] == "terminated_enabled")
    uid = next(u["id"] for u in entra["users"] if u["userPrincipalName"] == upn)
    ledger = env.ledger(lambda a: a["fix"] == "disable_account")
    ex = env.executor(ledger)
    ex.approve(None, "it.lead")
    env.faults(silent_ids=[uid])
    status = ex.run()
    assert status == {"verified": len(ledger.actions) - 1, "verify_failed": 1}
    failed = next(a for a in ledger.actions.values() if a.status == "verify_failed")
    assert failed.account == upn and failed.history[-1]["event"] == "verify_failed"


def test_crash_midway_then_rerun_does_not_repeat(env):
    ledger = env.ledger(lambda a: a["fix"] in ("remove_group_member", "remove_guest"))
    calls = Counter()

    def crash(a):
        calls["n"] += 1
        if calls["n"] == 10:
            raise RuntimeError("程序在寫入後當掉")

    ex = env.executor(ledger, after_write=crash)
    ex.approve(None, "it.lead")
    with pytest.raises(RuntimeError):
        ex.run(confirm_large=True)
    reloaded = Ledger(ledger.path)
    assert Counter(a.status for a in reloaded.actions.values())["executing"] == 1
    assert env.executor(reloaded).run(confirm_large=True) == {"verified": len(reloaded.actions)}
    s = env.stats()
    assert s["writes"] == len(reloaded.actions)  # 當掉那一筆重跑時發現已生效，沒有再寫一次


def test_tampered_action_is_refused(env):
    ledger = env.ledger(lambda a: a["fix"] == "remove_group_member")
    ex = env.executor(ledger)
    ex.approve(None, "it.lead")
    victim = next(iter(ledger.actions.values()))
    data = json.loads(ledger.path.read_text())
    data["actions"][0]["target"]["group_id"] = next(g["id"] for g in env.snapshot["entra"]["groups"]
                                                    if g["displayName"] == "SG-TPE-IT")
    ledger.path.write_text(json.dumps(data))
    reloaded = Ledger(ledger.path)
    env.executor(reloaded).run()
    assert reloaded.actions[victim.id].status == "refused"
    assert env.stats()["writes"] == len(ledger.actions) - 1


def test_protected_account_is_blocked_even_if_approved(env, entra):
    bg = next(u for u in entra["users"] if u["userPrincipalName"].startswith("bg-admin-01"))
    p = {"id": "x", "created_at": "", "manual": [], "actions": [asdict(Action(
        "bg1", "disable_account", "entra", bg["userPrincipalName"], "", "crafted", {"user_id": bg["id"]}, False))]}
    ledger = Ledger.create(env.tmp_path / "crafted.json", p)
    ex = env.executor(ledger)
    ex.approve(None, "someone")
    ex.run()
    assert ledger.actions["bg1"].status == "blocked" and env.stats()["writes"] == 0


def test_admin_cannot_be_disabled_before_role_removed(env, truth, entra):
    upn = next(i["account"] for i in truth["issues"] if i["type"] == "excess_admin")
    uid = next(u["id"] for u in entra["users"] if u["userPrincipalName"] == upn)
    p = {"id": "x", "created_at": "", "manual": [], "actions": [asdict(Action(
        "adm", "disable_account", "entra", upn, "", "crafted", {"user_id": uid}, False))]}
    ledger = Ledger.create(env.tmp_path / "admin.json", p)
    ex = env.executor(ledger)
    ex.approve(None, "it.lead")
    ex.run()
    assert ledger.actions["adm"].status == "blocked" and env.stats()["writes"] == 0


def test_rollback_restores_previous_state(env):
    ledger = env.ledger()
    ids = sample(ledger)
    ex = env.executor(ledger)
    ex.approve(ids, "it.lead", ack_irreversible=True)
    ex.run()
    assert all(ledger.actions[i].status == "verified" for i in ids)
    ex.rollback(ids, "it.lead")
    status = {ledger.actions[i].fix: ledger.actions[i].status for i in ids}
    assert status == {"disable_account": "rolled_back", "remove_group_member": "rolled_back",
                      "remove_guest": "rolled_back", "remove_role_assignment": "rolled_back",
                      "remove_github_member": "rolled_back_partial", "remove_outside_collaborator": "rollback_unsupported"}
    for i in ids:
        a = ledger.actions[i]
        if a.status == "rolled_back":
            assert ex.read(a)["present"] is True
