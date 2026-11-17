"""公司內部系統的匯出檔：HR 名冊、轉調、ERP 角色、職責分離例外、來賓與服務帳號登記。

示範環境讀 data/synthetic；正式環境換成 HRIS、ERP 的匯出即可，欄位相同。
"""

import csv
import json
from dataclasses import dataclass
from datetime import date
from pathlib import Path


def _rows(path: Path) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _date(s: str) -> date | None:
    return date.fromisoformat(s) if s else None


@dataclass
class Internal:
    hr: list[dict]
    transfers: list[dict]
    erp_roles: dict[str, set[str]]          # 角色 → 交易權限
    erp_assignments: dict[str, list[str]]   # 員工編號 → 角色
    mitigations: list[dict]
    guest_register: dict[str, dict]         # 來賓 Email（小寫）→ 登記
    service_accounts: dict[str, dict]       # UPN（小寫）→ 登記
    github_links: dict[str, str]            # GitHub 帳號（小寫）→ 員工編號


def load(data_dir: Path) -> Internal:
    hr = _rows(data_dir / "hr_employees.csv")
    for e in hr:
        e["hire_date"], e["termination_date"] = _date(e["hire_date"]), _date(e["termination_date"])
    transfers = _rows(data_dir / "hr_transfers.csv")
    for t in transfers:
        t["effective_date"], t["end_date"] = _date(t["effective_date"]), _date(t["end_date"])
    erp = json.loads((data_dir / "erp.json").read_text())
    assignments: dict[str, list[str]] = {}
    for a in erp["assignments"]:
        assignments.setdefault(a["user_id"], []).append(a["role"])
    mitigations = _rows(data_dir / "sod_mitigations.csv")
    for m in mitigations:
        m["expires_on"] = _date(m["expires_on"])
    guests = {g["guest_mail"].lower(): g | {"expires_on": _date(g["expires_on"])}
              for g in _rows(data_dir / "guest_register.csv")}
    services = {s["account"].lower(): s for s in _rows(data_dir / "service_accounts.csv")}
    links = {g["login"].lower(): g["employee_id"] for g in _rows(data_dir / "github_links.csv")}
    return Internal(hr, transfers, {r["code"]: set(r["transactions"]) for r in erp["roles"]}, assignments,
                    mitigations, guests, services, links)
