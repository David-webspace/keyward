import csv
import json
from collections import Counter
from datetime import date, datetime, timedelta

from app.seed.generate import AS_OF, ORG, POLICY, SEED, Gen

EXPECTED_ISSUES = {"terminated_enabled": 19, "terminated_github": 6, "transfer_residual": 30, "guest_access": 15,
                   "inactive_account": 20, "launch_overprovisioned": 18, "unlinked_github": 13, "github_no_2fa": 7,
                   "sod_conflict": 12, "peer_outlier": 15, "excess_admin": 5, "guest_github": 2}


def rows(path):
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def test_deterministic():
    a, b = Gen(SEED).run(), Gen(SEED).run()
    dump = lambda w: json.dumps([w["entra"], w["github"], w["ground_truth"]], default=str, sort_keys=True)
    assert dump(a) == dump(b)


def test_headcount_matches_org(world_dir):
    hr = [e for e in rows(world_dir / "hr_employees.csv") if e["status"] != "terminated"]
    assert len(hr) == 650
    got = Counter((e["site"], e["dept"]) for e in hr)
    want = {(s, d): n for s, v in ORG["sites"].items() for d, n in v["headcount"].items()}
    assert got == want


def test_issue_counts(truth):
    assert Counter(i["type"] for i in truth["issues"]) == EXPECTED_ISSUES


def test_unique_identifiers(world_dir, entra):
    upns = [u["userPrincipalName"].lower() for u in entra["users"]]
    assert len(upns) == len(set(upns))
    ids = [e["employee_id"] for e in rows(world_dir / "hr_employees.csv")]
    assert len(ids) == len(set(ids))


def test_issue_accounts_exist(world_dir, truth, entra):
    upns = {u["userPrincipalName"] for u in entra["users"]}
    gh = json.loads((world_dir / "github.json").read_text())
    logins = {m["login"] for m in gh["members"] + gh["outside_collaborators"]}
    erp_users = {a["user_id"] for a in json.loads((world_dir / "erp.json").read_text())["assignments"]}
    for i in truth["issues"]:
        pool = {"entra": upns, "github": logins, "erp": erp_users}[i["system"]]
        assert i["account"] in pool, i


def test_distractors_are_not_issues(truth):
    issue_accounts = {i["account"] for i in truth["issues"]}
    assert not issue_accounts & {d["account"] for d in truth["distractors"]}


def _hr_state(world_dir):
    hr = rows(world_dir / "hr_employees.csv")
    active_emails = {e["email"] for e in hr if e["status"] != "terminated"}
    return hr, active_emails


def test_terminated_enabled_matches_truth(world_dir, truth, entra):
    """離職（且沒有同 Email 的在職紀錄）但帳號仍啟用的人，必須剛好等於標準答案，不多不少。"""
    hr, active_emails = _hr_state(world_dir)
    left = {e["email"] for e in hr if e["status"] == "terminated"} - active_emails
    found = {u["userPrincipalName"] for u in entra["users"] if u["userPrincipalName"] in left and u["accountEnabled"]}
    assert found == {i["account"] for i in truth["issues"] if i["type"] == "terminated_enabled"}


def test_inactive_matches_truth(world_dir, truth, entra):
    hr, _ = _hr_state(world_dir)
    status = {e["email"]: e["status"] for e in hr if e["status"] != "terminated"}
    cutoff = AS_OF - timedelta(days=POLICY["inactivity_days"])
    grace = AS_OF - timedelta(days=POLICY["new_account_grace_days"])
    found = set()
    for u in entra["users"]:
        if status.get(u["userPrincipalName"]) != "active" or not u["accountEnabled"]:
            continue
        last = (u["signInActivity"] or {}).get("lastSignInDateTime")
        created = datetime.fromisoformat(u["createdDateTime"].rstrip("Z")).date()
        if created > grace:
            continue
        if last is None or datetime.fromisoformat(last.rstrip("Z")).date() < cutoff:
            found.add(u["userPrincipalName"])
    assert found == {i["account"] for i in truth["issues"] if i["type"] == "inactive_account"}


def test_sod_matches_truth(world_dir, truth):
    erp = json.loads((world_dir / "erp.json").read_text())
    tx = {r["code"]: set(r["transactions"]) for r in erp["roles"]}
    per_user: dict[str, set[str]] = {}
    for a in erp["assignments"]:
        per_user.setdefault(a["user_id"], set()).update(tx[a["role"]])
    mitigated = {(m["employee_id"], m["rule"]) for m in rows(world_dir / "sod_mitigations.csv")
                 if date.fromisoformat(m["expires_on"]) >= AS_OF}
    found = {(u, rule) for u, t in per_user.items() for rule, r in POLICY["sod_rules"].items()
             if r["left"] in t and r["right"] in t and (u, rule) not in mitigated}
    assert found == {(i["account"], i["rule"]) for i in truth["issues"] if i["type"] == "sod_conflict"}


def test_privileged_roles_outside_policy_match_truth(world_dir, truth, entra):
    hr = {e["email"]: e for e in rows(world_dir / "hr_employees.csv") if e["status"] != "terminated"}
    by_id = {u["id"]: u for u in entra["users"]}
    role_name = {d["id"]: d["displayName"] for d in entra["roleDefinitions"]}
    protected = {f"{a}@{ORG['domain']}" for a in POLICY["protected_accounts"]}
    found = set()
    for a in entra["roleAssignments"]:
        upn, role = by_id[a["principalId"]]["userPrincipalName"], role_name[a["roleDefinitionId"]]
        if upn in protected:
            continue
        e, rule = hr[upn], POLICY["privileged_roles"][role]
        ok = (e["dept"] in rule["departments"] and e["site"] in rule.get("sites", [e["site"]])
              and e["title"] in rule.get("titles", [e["title"]]) and e["employment_type"] == "regular")
        if not ok:
            found.add((upn, role))
    assert found == {(i["account"], i["role"]) for i in truth["issues"] if i["type"] == "excess_admin"}
