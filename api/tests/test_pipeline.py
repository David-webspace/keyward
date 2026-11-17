"""mock → 同步 → 發現規則 → 對照標準答案。"""

from dataclasses import asdict
from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.connectors.github import GitHubClient
from app.connectors.graph import GraphApp, GraphClient
from app.evals.score import run_pipeline, score
from app.findings import evaluate
from app.identity import Directory
from app.internal import load
from app.mock.main import create_app
from app.sync import empty_state, sync
from tests.conftest import ENV, graph_token


@pytest.fixture(scope="module")
def baseline(world_dir):
    return run_pipeline(world_dir)


def clients(http):
    graph = GraphClient(http, GraphApp("arcwell", ENV["MOCK_GRAPH_READER_ID"], ENV["MOCK_GRAPH_READER_SECRET"]),
                        "http://testserver", "http://testserver/login", sleep=lambda _: None)
    github = GitHubClient(http, "http://testserver/github", "arcwell-demo", ENV["MOCK_GITHUB_READ_TOKEN"],
                          sleep=lambda _: None)
    return graph, github


def keys(findings):
    return sorted((f.rule, f.account, f.fix, f.object) for f in findings)


def test_every_planted_issue_found_without_false_alarms(baseline):
    _, _, result = baseline
    assert result["found"] == result["expected"]
    assert result["false_positives"] == 0
    assert result["distractor_hits"] == []
    assert result["type_mismatches"] == []


def test_throttling_changes_nothing_but_retries(world_dir, baseline):
    _, findings, _ = baseline
    snap, throttled, _ = run_pipeline(world_dir, {"throttle_every": 4, "retry_after": 1})
    assert keys(throttled) == keys(findings)
    assert snap["stats"]["graph_retries"] > 0 and snap["stats"]["github_retries"] > 0


def test_incremental_sync_picks_up_fixes(world_dir, truth, entra):
    internal = load(world_dir)
    as_of = date.fromisoformat(truth["as_of"])
    with TestClient(create_app(world_dir, ENV)) as http:
        graph, github = clients(http)
        state = empty_state()
        first = evaluate(sync(graph, github, state), internal, as_of)

        writer = graph_token(http, writer=True)
        by_upn = {u["userPrincipalName"]: u["id"] for u in entra["users"]}
        gid = {g["displayName"]: g["id"] for g in entra["groups"]}
        term = next(i for i in truth["issues"] if i["type"] == "terminated_enabled")
        resid = next(i for i in truth["issues"] if i["type"] == "transfer_residual")
        http.patch(f"/v1.0/users/{by_upn[term['account']]}", json={"accountEnabled": False}, headers=writer)
        http.delete(f"/v1.0/groups/{gid[resid['group']]}/members/{by_upn[resid['account']]}/$ref", headers=writer)

        snap = sync(graph, github, state)
        second = evaluate(snap, internal, as_of)
    assert snap["mode"] == "incremental"
    assert snap["stats"] == snap["stats"] | {"user_changes": 1, "membership_changes": 1}
    gone = set(keys(first)) - set(keys(second))
    assert gone == {("terminated_enabled", term["account"], "disable_account", ""),
                    ("transfer_residual", resid["account"], "remove_group_member", resid["group"])}
    assert not set(keys(second)) - set(keys(first))


def test_free_tier_skips_inactivity_rule_only(world_dir, truth, baseline):
    _, findings, _ = baseline
    snap, free, _ = run_pipeline(world_dir, {"premium": False})
    assert snap["entra"]["sign_in_available"] is False
    assert keys(free) == [k for k in keys(findings) if k[0] != "inactive_account"]


def test_expired_token_is_refreshed(world_dir):
    with TestClient(create_app(world_dir, ENV)) as http:
        graph, _ = clients(http)
        graph.get("/v1.0/users?$top=1")
        http.app.state.store.tokens.clear()  # 模擬 token 過期
        assert len(graph.get("/v1.0/users?$top=1")["value"]) == 1


def test_identity_handles_rehire_and_converted_contract(world_dir, truth, entra):
    ident = Directory(load(world_dir))
    users = {u["userPrincipalName"]: u for u in entra["users"]}
    for d in truth["distractors"]:
        if d["type"] in ("rehired", "contract_converted"):
            m = ident.entra(users[d["account"]])
            assert m.kind == "employee" and m.record["employee_id"] == d["employee_id"]
            assert m.record["status"] != "terminated"


def test_unlinked_github_is_never_auto_removed(baseline):
    _, findings, _ = baseline
    unlinked = [f for f in findings if f.rule == "unlinked_github"]
    assert unlinked and all(f.fix == "confirm_identity" and not f.confirmed for f in unlinked)
    assert any(f.evidence["suggestion"] for f in unlinked)  # 有填姓名的，會附上候選人


def test_score_counts_wrong_object_as_miss(baseline, truth):
    _, findings, _ = baseline
    f = next(f for f in findings if f.rule == "transfer_residual")
    tampered = [type(f)(**(asdict(f) | {"object": "SG-XXX-WRONG"}))] + [x for x in findings if x is not f]
    result = score(tampered, truth)
    assert result["found"] == result["expected"] - 1 and result["false_positives"] == 1
