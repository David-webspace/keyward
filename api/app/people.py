"""單一員工的跨系統權限全貌：HR、Entra（直接與間接群組、角色、登入）、GitHub、ERP，以及相關發現。"""

from collections import defaultdict

from app.findings import Finding
from app.identity import Directory


def profile(emp_id: str, snapshot: dict, ident: Directory, findings: list[Finding]) -> dict | None:
    e = ident.by_id.get(emp_id)
    if e is None:
        return None
    e = ident.current(e)
    entra = snapshot["entra"]
    gname = {g["id"]: g for g in entra["groups"]}
    parents, direct = defaultdict(set), defaultdict(set)
    for gid, ms in entra["members"].items():
        for m in ms:
            (direct if m["type"] == "user" else parents)[m["id"]].add(gid)
    role_name = {d["id"]: d["displayName"] for d in entra["roleDefinitions"]}

    accounts = []
    for u in entra["users"]:
        m = ident.entra(u)
        if m.kind != "employee" or m.record["employee_id"] != e["employee_id"]:
            continue
        via: dict[str, list[str]] = {}
        for root in direct[u["id"]]:
            stack, seen = [root], set()
            while stack:
                g = stack.pop()
                if g in seen:
                    continue
                seen.add(g)
                if g != root:
                    via.setdefault(g, []).append(gname[root]["displayName"])
                stack += parents[g]
        accounts.append({
            "upn": u["userPrincipalName"], "enabled": u.get("accountEnabled"), "matched_by": m.method,
            "last_sign_in": (u.get("signInActivity") or {}).get("lastSignInDateTime"),
            "direct_groups": sorted(({"name": gname[g]["displayName"], "description": gname[g].get("description")}
                                     for g in direct[u["id"]]), key=lambda x: x["name"]),
            "inherited_groups": sorted(({"name": gname[g]["displayName"], "via": sorted(v)} for g, v in via.items()
                                        if g not in direct[u["id"]]), key=lambda x: x["name"]),
            "roles": sorted(role_name[a["roleDefinitionId"]] for a in entra["roleAssignments"] if a["principalId"] == u["id"]),
        })

    github = []
    for kind, accts in (("member", snapshot["github"]["members"]), ("outside", snapshot["github"]["outside_collaborators"])):
        for a in accts:
            m = ident.github(a)
            if m.kind == "employee" and m.record["employee_id"] == e["employee_id"]:
                github.append({"login": a["login"], "kind": kind, "role": a.get("role"), "two_factor": a.get("two_factor"),
                               "matched_by": m.method, "confirmed": m.confirmed})

    erp = [{"role": r, "transactions": sorted(ident.internal.erp_roles[r])}
           for r in ident.internal.erp_assignments.get(e["employee_id"], [])]
    manager = ident.by_id.get(e["manager_id"])
    return {
        "employee_id": e["employee_id"], "name": e["display"], "en_name": e["en_name"], "email": e["email"],
        "site": e["site"], "dept": e["dept"], "title": e["title"], "status": e["status"],
        "employment_type": e["employment_type"], "hire_date": str(e["hire_date"]),
        "termination_date": str(e["termination_date"]) if e["termination_date"] else None,
        "manager": manager and {"employee_id": manager["employee_id"], "name": manager["display"]},
        "transfers": [{k: str(v) if v else None for k, v in t.items()} for t in ident.internal.transfers
                      if t["employee_id"] == e["employee_id"]],
        "entra": accounts, "github": github, "erp": erp,
        "findings": [{"rule": f.rule, "system": f.system, "account": f.account, "object": f.object, "fix": f.fix}
                     for f in findings if f.employee_id == e["employee_id"]],
    }
