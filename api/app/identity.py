"""身分對應：把各平台帳號對回 HR 名冊上的一個人。

Entra：employeeId（含轉正前的舊編號）→ UPN／mail。同一 Email 有多筆紀錄（重新聘用）時，以在職那筆為準。
GitHub：IT 的帳號登記表或公開 Email 完全相符才算確認；只有姓名或帳號名稱相符的列為「候選」，必須由人確認。
"""

import re
from dataclasses import dataclass

from app.internal import Internal


@dataclass
class Match:
    kind: str                 # employee / service / guest / unknown
    record: dict | None       # HR 紀錄、服務帳號登記或來賓登記
    method: str               # 用什麼對上的
    confirmed: bool = True    # False = 只是候選，需人工確認


def _norm(s: str | None) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


class Directory:
    def __init__(self, internal: Internal):
        self.internal = internal
        self.by_id: dict[str, dict] = {}
        self.by_email: dict[str, dict] = {}
        for e in internal.hr:
            self.by_id[e["employee_id"]] = e
            if e["legacy_id"]:
                self.by_id[e["legacy_id"]] = e
            cur = self.by_email.get(e["email"].lower())
            if cur is None or (cur["status"] == "terminated" and e["status"] != "terminated"):
                self.by_email[e["email"].lower()] = e
        names: dict[str, list[dict]] = {}
        handles: dict[str, list[dict]] = {}
        for e in self.by_email.values():
            names.setdefault(_norm(e["en_name"]), []).append(e)
            parts = e["en_name"].split()
            given, surname = _norm(" ".join(parts[:-1])), _norm(parts[-1])
            for h in {given + surname, given[:1] + surname}:
                handles.setdefault(h, []).append(e)
        self.names = {k: v[0] for k, v in names.items() if len(v) == 1}
        self.handles = {k: v[0] for k, v in handles.items() if len(v) == 1}

    def current(self, e: dict) -> dict:
        """同一 Email 若有在職紀錄，回傳在職那筆（重新聘用的情況）。"""
        return self.by_email.get(e["email"].lower(), e)

    def entra(self, u: dict) -> Match:
        upn = (u.get("userPrincipalName") or "").lower()
        if u.get("userType") == "Guest":
            reg = self.internal.guest_register.get((u.get("mail") or "").lower())
            return Match("guest", reg, "guest_register" if reg else "unregistered")
        if upn in self.internal.service_accounts:
            return Match("service", self.internal.service_accounts[upn], "service_registry")
        if u.get("employeeId") in self.by_id:
            e = self.by_id[u["employeeId"]]
            method = "legacy_id" if e["legacy_id"] == u["employeeId"] else "employee_id"
            return Match("employee", self.current(e), method)
        for key in (upn, (u.get("mail") or "").lower()):
            if key in self.by_email:
                return Match("employee", self.by_email[key], "email")
        return Match("unknown", None, "none")

    def github(self, account: dict) -> Match:
        linked = self.internal.github_links.get(account["login"].lower())
        if linked in self.by_id:
            return Match("employee", self.current(self.by_id[linked]), "github_links")
        email = (account.get("email") or "").lower()
        if email in self.by_email:
            return Match("employee", self.by_email[email], "email")
        if email in self.internal.guest_register:
            return Match("guest", self.internal.guest_register[email], "guest_email")
        name = _norm(account.get("name"))
        if name and name in self.names:
            return Match("employee", self.names[name], "name", confirmed=False)
        login = _norm(re.sub(r"-arcwell$", "", account["login"]))
        if login in self.handles:
            return Match("employee", self.handles[login], "login", confirmed=False)
        return Match("unknown", None, "none")
