"""發現規則：輸入同步快照與內部系統資料，依 policy.yaml 判定。全部是確定性的規則與統計，不經過模型。

每筆發現都帶「建議的修正動作」與「要動的物件」，同一個根因（例如某個直接加入的群組）只會出現一次，
它造成的多個敏感資源存取寫在 evidence 裡。

python -m app.findings [--snapshot 路徑] [--as-of 2026-11-16]
"""

import argparse
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from app.identity import Directory, Match
from app.internal import Internal, load

POLICY = yaml.safe_load((Path(__file__).with_name("policy.yaml")).read_text())


@dataclass
class Finding:
    rule: str
    system: str
    account: str
    fix: str
    object: str = ""
    employee_id: str | None = None
    confirmed: bool = True      # False = 身分只是候選對應，處理前要人確認
    evidence: dict = field(default_factory=dict)


def _day(ts: str | None) -> date | None:
    return datetime.fromisoformat(ts.rstrip("Z")).date() if ts else None


def _allowed(attrs: list[tuple[str, str]], rule: dict) -> bool:
    return any(d in rule["departments"] and (not rule.get("sites") or s in rule["sites"]) for s, d in attrs)


def evaluate(snapshot: dict, internal: Internal, as_of: date, policy: dict = POLICY) -> list[Finding]:
    ident = Directory(internal)
    entra, gh = snapshot["entra"], snapshot["github"]
    users = {u["id"]: u for u in entra["users"]}
    gname = {g["id"]: g["displayName"] for g in entra["groups"]}
    out: list[Finding] = []

    direct: dict[str, set[str]] = defaultdict(set)     # 使用者 → 直接加入的群組
    parents: dict[str, set[str]] = defaultdict(set)    # 群組 → 包含它的群組
    for gid, ms in entra["members"].items():
        for m in ms:
            (direct if m["type"] == "user" else parents)[m["id"]].add(gid)

    def reach(uid: str) -> dict[str, set[str]]:
        """使用者能間接取得的每個群組 → 帶來這個存取的直接群組（根因）。"""
        got: dict[str, set[str]] = defaultdict(set)
        for root in direct[uid]:
            stack, seen = [root], set()
            while stack:
                g = stack.pop()
                if g in seen:
                    continue
                seen.add(g)
                got[g].add(root)
                stack += parents[g]
        return got

    temps = defaultdict(list)
    for t in internal.transfers:
        if t["kind"] == "temporary" and t["effective_date"] <= as_of <= t["end_date"]:
            temps[t["employee_id"]].append((t["to_site"], t["to_dept"]))
    permanent = defaultdict(list)
    for t in internal.transfers:
        if t["kind"] == "permanent":
            permanent[t["employee_id"]].append(t)

    org_re = re.compile(policy["org_group_pattern"])
    sites = {e["site"] for e in internal.hr}
    depts = {e["dept"] for e in internal.hr}

    def org_unit(gid: str) -> tuple[str, str] | None:
        m = org_re.match(gname.get(gid, ""))
        return (m["site"], m["dept"]) if m and m["site"] in sites and m["dept"] in depts else None

    def left(e: dict) -> bool:
        return e["status"] == "terminated" and e["termination_date"] and e["termination_date"] <= as_of

    def guest_problem(reg: dict | None) -> str | None:
        if reg is None:
            return "unregistered"
        if reg["expires_on"] < as_of:
            return "expired"
        sponsor = ident.by_id.get(reg["sponsor_employee_id"])
        return "sponsor_left" if sponsor and left(ident.current(sponsor)) else None

    matches: dict[str, Match] = {uid: ident.entra(u) for uid, u in users.items()}
    cutoff = as_of - timedelta(days=policy["inactivity_days"])
    grace = as_of - timedelta(days=policy["new_account_grace_days"])
    transfer_grace = as_of - timedelta(days=policy["transfer_grace_days"])
    explained: dict[str, set[str]] = defaultdict(set)   # 已經被其他規則處理的直接群組，不再算進同儕離群

    for uid, u in users.items():
        m = matches[uid]
        upn = u["userPrincipalName"]
        if not u.get("accountEnabled"):
            continue

        if m.kind == "guest":
            reg = m.record
            reason = guest_problem(reg)
            if reason:
                out.append(Finding("guest_access", "entra", upn, "remove_guest", evidence={"reason": reason, "register": reg and
                                                                                             {k: str(v) for k, v in reg.items()}}))
                continue
            # 來賓沒有部門：能間接存取任何限制資源都不合理，除非該資源的規則明確允許來賓
            by_root: dict[str, list[str]] = defaultdict(list)
            for gid, roots in reach(uid).items():
                rule = policy["resources"].get(gname.get(gid))
                if rule and not rule.get("guests"):
                    for root in roots:
                        by_root[root].append(gname[gid])
            for root, res in by_root.items():
                out.append(Finding("guest_resource", "entra", upn, "remove_group_member", gname[root],
                                   evidence={"grants": sorted(res), "guest": u.get("mail")}))
            continue
        if m.kind != "employee":
            continue
        e = m.record
        if left(e):
            out.append(Finding("terminated_enabled", "entra", upn, "disable_account", employee_id=e["employee_id"],
                               evidence={"terminated_on": str(e["termination_date"]), "matched_by": m.method,
                                         "last_sign_in": (u.get("signInActivity") or {}).get("lastSignInDateTime")}))
            continue

        # 殭屍帳號（需要 signInActivity；留職停薪不適用）
        if entra["sign_in_available"] and e["status"] == "active" and _day(u["createdDateTime"]) <= grace:
            last = _day((u.get("signInActivity") or {}).get("lastSignInDateTime"))
            if last is None or last < cutoff:
                out.append(Finding("inactive_account", "entra", upn, "disable_account", employee_id=e["employee_id"],
                                   evidence={"last_sign_in": str(last) if last else None}))

        attrs = [(e["site"], e["dept"])] + temps[e["employee_id"]]

        # 轉調未收回：直接加入的組織群組和現職不符
        residual: dict[str, Finding] = {}
        for gid in direct[uid]:
            unit = org_unit(gid)
            if unit is None or unit in attrs:
                continue
            record = next((t for t in permanent[e["employee_id"]] if (t["from_site"], t["from_dept"]) == unit), None)
            if record and record["effective_date"] > transfer_grace:
                attrs.append(unit)  # 寬限期內：舊單位的權限（含間接取得的資源）暫時都算合理
                explained[uid].add(gid)
                continue
            f = Finding("transfer_residual", "entra", upn, "remove_group_member", gname[gid], e["employee_id"],
                        evidence={"current": f"{e['site']}-{e['dept']}",
                                  "transfer": record and {k: str(v) for k, v in record.items()}, "grants": []})
            residual[gid] = f
            explained[uid].add(gid)
            out.append(f)

        # 敏感資源：依根因（直接加入的群組）合併
        by_root: dict[str, list[str]] = defaultdict(list)
        for gid, roots in reach(uid).items():
            rule = policy["resources"].get(gname.get(gid))
            if rule and not _allowed(attrs, rule):
                for root in roots:
                    by_root[root].append(gname[gid])
        for root, res in by_root.items():
            if root in residual:
                residual[root].evidence["grants"] = sorted(res)
                continue
            explained[uid].add(root)
            out.append(Finding("resource_access", "entra", upn, "remove_group_member", gname[root], e["employee_id"],
                               evidence={"grants": sorted(res), "current": f"{e['site']}-{e['dept']}"}))

    # 特權角色
    role_name = {d["id"]: d["displayName"] for d in entra["roleDefinitions"]}
    protected = {a.lower() for a in policy["protected_accounts"]}
    for a in entra["roleAssignments"]:
        u = users.get(a["principalId"])
        if u is None or u["userPrincipalName"].split("@")[0].lower() in protected:
            continue
        role, m = role_name[a["roleDefinitionId"]], matches[a["principalId"]]
        rule = policy["privileged_roles"].get(role)
        e = m.record if m.kind == "employee" else None
        ok = e is not None and rule is not None and not left(e) and e["employment_type"] == "regular" and \
            e["dept"] in rule["departments"] and e["site"] in rule.get("sites", [e["site"]]) and \
            e["title"] in rule.get("titles", [e["title"]])
        if not ok:
            out.append(Finding("excess_admin", "entra", u["userPrincipalName"], "remove_role_assignment", role,
                               e and e["employee_id"], evidence={"assignment_id": a["id"],
                                                                 "holder": e and f"{e['site']}-{e['dept']} {e['title']} ({e['employment_type']})"}))

    # 同儕離群：同部門同職稱（不足時改用同部門）的人裡，幾乎沒人有的直接群組
    active = {uid: matches[uid].record for uid, u in users.items()
              if u.get("accountEnabled") and matches[uid].kind == "employee" and not left(matches[uid].record)}

    def plain(uid: str) -> set[str]:
        return {g for g in direct[uid] if org_unit(g) is None}

    cohorts: dict[tuple, list[str]] = defaultdict(list)
    for uid, e in active.items():
        cohorts[(e["dept"], e["title"])].append(uid)
        cohorts[(e["dept"],)].append(uid)
    for uid, e in active.items():
        peers, cohort = [p for p in cohorts[(e["dept"], e["title"])] if p != uid], "title"
        if len(peers) < policy["peer_min_size"]:
            peers, cohort = [p for p in cohorts[(e["dept"],)] if p != uid], "dept"
        share = Counter(g for p in peers for g in plain(p))
        rare = sorted(gname[g] for g in plain(uid) - explained[uid] if share[g] / len(peers) < policy["peer_rare_share"])
        if len(rare) >= policy["peer_min_rare"]:
            out.append(Finding("peer_outlier", "entra", users[uid]["userPrincipalName"], "review_groups",
                               employee_id=e["employee_id"], evidence={"groups": rare, "peers": len(peers), "cohort": cohort}))

    # ERP 職責分離
    mitigated = {(m["employee_id"], m["rule"]) for m in internal.mitigations if m["expires_on"] >= as_of}
    for emp, roles in internal.erp_assignments.items():
        tx = set().union(*(internal.erp_roles[r] for r in roles))
        for rid, rule in policy["sod_rules"].items():
            if rule["left"] in tx and rule["right"] in tx and (emp, rid) not in mitigated:
                culprits = [r for r in roles if rule["right"] in internal.erp_roles[r]]
                out.append(Finding("sod_conflict", "erp", emp, "remove_erp_role", rid, emp,
                                   evidence={"conflict": rule["zh"], "roles": roles, "suggest_remove": culprits}))

    # GitHub
    for kind, accounts in (("member", gh["members"]), ("outside_collaborator", gh["outside_collaborators"])):
        for a in accounts:
            m = ident.github(a)
            fix = "remove_github_member" if kind == "member" else "remove_outside_collaborator"
            ev = {"kind": kind, "matched_by": m.method}
            if m.kind == "guest":
                if reason := guest_problem(m.record):
                    out.append(Finding("guest_github", "github", a["login"], fix,
                                       evidence=ev | {"reason": reason, "guest": m.record["guest_mail"]}))
                continue
            if m.kind == "unknown" or not m.confirmed:
                # 對不上登記表或 Email：不直接移除，先請人確認是誰的帳號（有候選就附上）
                suggestion = m.record and {"employee_id": m.record["employee_id"], "name": m.record["en_name"],
                                           "status": m.record["status"]}
                out.append(Finding("unlinked_github", "github", a["login"], "confirm_identity", confirmed=False,
                                   evidence=ev | {"removal_fix": fix, "suggestion": suggestion}))
            elif left(m.record):
                out.append(Finding("terminated_github", "github", a["login"], fix, employee_id=m.record["employee_id"],
                                   evidence=ev | {"terminated_on": str(m.record["termination_date"])}))
            elif kind == "member" and not a.get("two_factor", True):
                out.append(Finding("github_no_2fa", "github", a["login"], "require_2fa", employee_id=m.record["employee_id"],
                                   evidence=ev))
    return out


def main():
    from app.sync import DATA
    ap = argparse.ArgumentParser()
    ap.add_argument("--snapshot", type=Path)
    ap.add_argument("--as-of", type=date.fromisoformat, default=date.today())
    args = ap.parse_args()
    snap_path = args.snapshot or max((DATA / "state" / "snapshots").glob("*.json"))
    findings = evaluate(json.loads(snap_path.read_text()), load(DATA / "synthetic"), args.as_of)
    out = DATA / "state" / "findings.json"
    out.write_text(json.dumps([asdict(f) for f in findings], ensure_ascii=False, indent=1))
    print(json.dumps({"snapshot": str(snap_path), "findings": len(findings),
                      "by_rule": Counter(f.rule for f in findings)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
