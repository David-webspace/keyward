"""Arcwell Electronics 擬真資料（固定種子，可重現）。人名、公司、帳號全部虛構，Email 一律用保留網域 .example。

產出 data/synthetic/：
- hr_employees.csv、hr_transfers.csv：HR 名冊，唯一權威來源
- entra.json：Graph 形狀的使用者、群組、成員、目錄角色
- github.json：GitHub organization 成員、外部協作者、團隊
- erp.json、sod_mitigations.csv：ERP 角色指派與職責分離例外核准
- guest_register.csv、service_accounts.csv、github_links.csv：IT 維護的外部來賓、服務帳號、GitHub 帳號登記
- ground_truth.json：刻意埋入的問題（評測標準答案）與干擾項（不該被報出來）
- manifest.json：各項數量

python -m app.seed.generate
"""

import csv
import json
import os
import random
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from pathlib import Path

import yaml

from app.seed.names import ascii_fold, person

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
OUT = Path(os.environ.get("DATA_DIR", ROOT / "data")) / "synthetic"
ORG = yaml.safe_load((HERE / "org.yaml").read_text())
POLICY = yaml.safe_load((HERE.parent / "policy.yaml").read_text())
SEED = 20261116
NS = uuid.UUID("6f1c2a52-6b0e-4f7e-9a51-2a7d3c4e5b60")
AS_OF: date = ORG["as_of"]
DOMAIN = ORG["domain"]
GITHUB_ORG = "arcwell-demo"

# Entra 內建角色的 templateId（微軟公開、所有租戶相同）
ROLE_IDS = {
    "Global Administrator": "62e90394-69f5-4237-9190-012177145e10",
    "Privileged Role Administrator": "e8611ab8-c189-46e8-94e1-60213ab1f814",
    "User Administrator": "fe930be7-5e62-47db-91af-98c3a49a38b1",
    "Groups Administrator": "fdd7a751-b60b-444a-984c-02652fe8fa1c",
    "Application Administrator": "9b895d92-2cd3-44c7-9d02-a6ac2d5ea5c3",
    "Exchange Administrator": "29232cdf-9323-42fd-ade2-1d097af3e4de",
    "SharePoint Administrator": "f28a1f50-f6e7-4571-818b-6a12f2af6b6c",
    "Helpdesk Administrator": "729827e3-9c14-49f7-bb1b-9608f156bbb8",
    "Security Reader": "5d6b6bb7-de71-4623-b4af-96380a352509",
}

ERP_ROLES = {
    "FIN_AP_CLERK": ("應付帳款專員", ["AP_INVOICE", "REPORT_FIN"]),
    "FIN_AP_MANAGER": ("應付帳款主管", ["PAY_APPROVE", "REPORT_FIN"]),
    "FIN_TREASURY": ("出納", ["PAY_RUN", "REPORT_FIN"]),
    "FIN_AR_CLERK": ("應收帳款專員", ["AR_INVOICE", "REPORT_FIN"]),
    "FIN_AR_MANAGER": ("應收帳款主管", ["CREDIT_MEMO", "REPORT_FIN"]),
    "FIN_GL_ACCOUNTANT": ("總帳會計", ["GL_POST", "REPORT_FIN"]),
    "FIN_CONTROLLER": ("財務長室", ["GL_CLOSE", "COST_RUN", "REPORT_FIN"]),
    "FIN_ASSET": ("固定資產", ["ASSET_MAINT"]),
    "COST_ANALYST": ("成本分析", ["COST_RUN"]),
    "SC_VENDOR_MASTER": ("供應商主檔維護", ["VENDOR_MAINT"]),
    "SC_BUYER": ("採購", ["PO_CREATE", "REPORT_OPS"]),
    "SC_PO_APPROVER": ("採購核准", ["PO_APPROVE", "REPORT_OPS"]),
    "SC_MATERIAL_MASTER": ("料號主檔維護", ["MAT_MAINT"]),
    "WH_RECEIVER": ("收貨", ["GR_POST"]),
    "WH_SHIPPER": ("出貨", ["GI_POST"]),
    "WH_INVENTORY_CTRL": ("庫存管制", ["INV_ADJUST", "INV_COUNT"]),
    "WH_COUNTER": ("盤點", ["INV_COUNT"]),
    "SD_ORDER_ENTRY": ("訂單登錄", ["SO_CREATE", "REPORT_OPS"]),
    "SD_ORDER_APPROVER": ("訂單核准", ["SO_APPROVE"]),
    "SD_CUSTOMER_MASTER": ("客戶主檔維護", ["CUST_MAINT"]),
    "SD_PRICING": ("價格維護", ["PRICE_MAINT"]),
    "QA_INSPECTOR": ("品檢", ["QC_BLOCK"]),
    "QA_RELEASE": ("品質放行", ["QC_RELEASE"]),
    "MFG_PLANNER": ("生產排程", ["PROD_ORDER", "REPORT_OPS"]),
    "MFG_SUPERVISOR": ("生產報工", ["PROD_CONFIRM", "REPORT_OPS"]),
    "ENG_BOM": ("BOM 維護", ["BOM_MAINT"]),
    "IT_ERP_ADMIN": ("ERP 帳號管理", ["USER_ADMIN"]),
    "RPT_FIN_VIEWER": ("財務報表檢視", ["REPORT_FIN"]),
    "RPT_OPS_VIEWER": ("營運報表檢視", ["REPORT_OPS"]),
    "EXEC_VIEWER": ("高階主管檢視", ["REPORT_FIN", "REPORT_OPS"]),
}
ERP_BY_TITLE = {
    "Accountant": ["FIN_GL_ACCOUNTANT"], "AP Specialist": ["FIN_AP_CLERK"], "AR Specialist": ["FIN_AR_CLERK"],
    "Treasury Analyst": ["FIN_TREASURY"], "Cost Analyst": ["COST_ANALYST"], "Finance Manager": ["FIN_CONTROLLER", "FIN_AP_MANAGER"],
    "Buyer": ["SC_BUYER"], "Material Planner": ["SC_MATERIAL_MASTER", "RPT_OPS_VIEWER"],
    "Vendor Master Specialist": ["SC_VENDOR_MASTER"], "Supply Chain Manager": ["SC_PO_APPROVER"],
    "Warehouse Clerk": ["WH_COUNTER"], "Shipping Coordinator": ["WH_SHIPPER"], "Receiving Clerk": ["WH_RECEIVER"],
    "Warehouse Manager": ["WH_INVENTORY_CTRL", "RPT_OPS_VIEWER"],
    "Order Administrator": ["SD_ORDER_ENTRY"], "Account Manager": ["RPT_OPS_VIEWER"],
    "Sales Operations Specialist": ["SD_CUSTOMER_MASTER"], "Sales Manager": ["SD_ORDER_APPROVER", "SD_PRICING"],
    "QC Inspector": ["QA_INSPECTOR"], "Quality Engineer": ["QA_INSPECTOR"], "Quality Manager": ["QA_RELEASE"],
    "Production Planner": ["MFG_PLANNER"], "Production Supervisor": ["MFG_SUPERVISOR"],
    "Plant Manager": ["MFG_SUPERVISOR", "RPT_OPS_VIEWER"],
    "Component Engineer": ["ENG_BOM"], "Hardware Engineering Manager": ["ENG_BOM"],
    "ERP Analyst": ["IT_ERP_ADMIN"],
    "Chief Executive Officer": ["EXEC_VIEWER"], "Vice President": ["EXEC_VIEWER"],
}

# 某些據點部門一定要有的職稱人數（讓後面的情境一定挑得到人）
REQUIRED_TITLES = {
    ("TPE", "SC"): {"Vendor Master Specialist": 2, "Buyer": 4},
    ("TPE", "FIN"): {"Treasury Analyst": 2, "AP Specialist": 3, "AR Specialist": 2, "Accountant": 3},
    ("TPE", "IT"): {"ERP Analyst": 3, "System Engineer": 5, "Helpdesk Engineer": 2, "Network Engineer": 1},
    ("TPE", "SALES"): {"Sales Operations Specialist": 2, "Order Administrator": 3, "Account Manager": 5},
    ("TPE", "EXEC"): {"Vice President": 3},
    ("TPE", "LEGAL"): {"Compliance Specialist": 2},
    ("TYN", "MFG"): {"Production Planner": 2, "Production Supervisor": 4, "Process Technician": 10},
    ("TYN", "WH"): {"Shipping Coordinator": 3},
    ("DGN", "WH"): {"Shipping Coordinator": 2},
    ("DGN", "SC"): {"Buyer": 4},
    ("BNH", "FIN"): {"AP Specialist": 1},
    ("CBI", "WH"): {"Shipping Coordinator": 2},
}

PRJ_THEMES = {
    "RDHW": ["PSU-650W", "GaN-Charger-140W", "Server-PSU-3kW", "LED-Driver-Gen4", "EV-OBC-11kW",
             "Adapter-USB-PD", "Telecom-Rectifier", "Solar-Microinverter", "Medical-PSU", "DC-DC-Brick"],
    "RDFW": ["PMBus-Stack", "Bootloader-v3", "OTA-Update", "Digital-Control-Loop", "Fan-Control",
             "Secure-Boot", "Telemetry-Agent", "Calibration-Tool"],
    "TEST": ["ATE-Migration", "Burn-in-Automation", "HiPot-Station", "Fixture-Library", "Test-Data-Lake"],
    "MFG": ["SMT-Line-Upgrade", "Lean-TYN-2026", "Yield-Taskforce", "AOI-Rollout", "CBI-Line-Ramp", "Kaizen-DGN"],
    "QA": ["IATF-Audit-2026", "8D-Customer-Returns", "Supplier-Quality-Scorecard", "ISO14001-Renewal", "Reliability-Lab"],
    "SC": ["Dual-Sourcing-2026", "VMI-Pilot", "Tariff-Impact", "Supplier-Portal"],
    "SALES": ["Key-Account-Hyperscaler", "EU-Distributor-Onboarding", "Japan-Auto-Tier1", "Pricing-Review-2027",
              "Trade-Show-APEC", "CRM-Cleanup"],
    "FAE": ["Design-In-Support", "Reference-Design-Kit", "Customer-Lab-Tours"],
    "IT": ["M365-Migration", "MES-Upgrade", "ERP-S4-Readiness", "Zero-Trust-Network", "Laptop-Refresh-2026"],
    "FIN": ["Budget-2027", "Transfer-Pricing", "Audit-FY2025"],
    "HR": ["Talent-Review-2026", "CBI-Hiring-Wave"],
    "LEGAL": ["Export-Control-Review"],
    "WH": ["WMS-Barcode", "Warehouse-Layout-TYN"],
}
CODENAMES = ["Atlas", "Kestrel", "Nimbus", "Orion", "Falcon", "Juniper", "Cobalt", "Vega", "Lumen", "Titan",
             "Aurora", "Sierra", "Helix", "Quartz", "Zephyr", "Beacon", "Comet", "Ember", "Glacier", "Harbor"]

MISC_GROUPS = [
    ("DL-All-Arcwell", "全公司公告"), ("SG-Printers-TPE", "台北印表機"), ("SG-Printers-HSC", "新竹印表機"),
    ("Club-Taipei-Badminton", "台北羽球社"), ("Club-Hsinchu-Running", "新竹路跑社"), ("M365-Copilot-Pilot", "Copilot 試用"),
    ("Legacy-Lotus-Migration", ""), ("Test-Group-1", ""), ("Test-Group-2", ""), ("Old-SharePoint-Owners", ""),
    ("EXT-Auditors", "外部稽核人員"), ("EXT-Firmware-Partners", "韌體外包夥伴"), ("EXT-Logistics-Partners", "物流夥伴"),
    ("EXT-Customer-Portal", "客戶入口網站"), ("SG-Visitors-TPE", "台北訪客"), ("Training-ISO27001-2026", "資安教育訓練"),
    ("Training-Safety-TYN", "桃園廠工安訓練"), ("Committee-Welfare", "職工福利委員會"), ("Committee-ESG", "ESG 委員會"),
    ("SG-Remote-Workers", "遠端工作"), ("SG-Laptop-Pilot", ""), ("SG-Intern-2026", "2026 實習生"),
    ("Temp-Audit-2025", ""), ("SG-Kiosk-Devices", "產線共用機台"), ("SG-Mobile-Devices", "公務手機"),
]

GUEST_COMPANIES = [
    ("kestrel-audit.example", "外部稽核", "QA", 8), ("brightline-design.example", "外包設計", "RDHW", 8),
    ("deltacore-fw.example", "韌體外包", "RDFW", 10), ("sunfield-logistics.example", "物流", "WH", 8),
    ("novaterm.example", "客戶", "SALES", 8), ("helios-power.example", "客戶", "SALES", 6),
    ("orbital-it.example", "IT 委外", "IT", 7), ("pacific-legal.example", "法律顧問", "LEGAL", 5),
]


def oid(kind: str, key: str) -> str:
    return str(uuid.uuid5(NS, f"{kind}:{key}"))


class Gen:
    def __init__(self, seed: int):
        self.rng = random.Random(seed)
        self.emails: set[str] = set()
        self.ids = iter(self.rng.sample(range(10001, 39999), 2000))
        self.special: set[str] = set()
        self.issues: list[dict] = []
        self.distractors: list[dict] = []

    # ---------- 小工具 ----------
    def date_between(self, a: date, b: date) -> date:
        return a + timedelta(days=self.rng.randint(0, (b - a).days))

    def ts(self, d: date) -> str:
        r = self.rng
        return datetime(d.year, d.month, d.day, r.randint(0, 13), r.randint(0, 59), r.randint(0, 59)).strftime("%Y-%m-%dT%H:%M:%SZ")

    def req_id(self) -> str:
        return str(uuid.UUID(int=self.rng.getrandbits(128)))

    def sign_in(self, last: date | None, non_interactive: date | None = None) -> dict | None:
        if last is None and non_interactive is None:
            return None
        li = self.ts(last) if last else None
        ni = self.ts(non_interactive) if non_interactive else None
        return {"lastSignInDateTime": li, "lastSignInRequestId": self.req_id() if li else None,
                "lastNonInteractiveSignInDateTime": ni, "lastNonInteractiveSignInRequestId": self.req_id() if ni else None,
                "lastSuccessfulSignInDateTime": li, "lastSuccessfulSignInRequestId": self.req_id() if li else None}

    def email(self, local: str) -> str:
        e, n = f"{local}@{DOMAIN}", 2
        while e in self.emails:
            e, n = f"{local}{n}@{DOMAIN}", n + 1
        self.emails.add(e)
        return e

    def pick(self, cands: list[dict], k: int, why: str) -> list[dict]:
        pool = [e for e in cands if e["employee_id"] not in self.special and not e["is_manager"]]
        if len(pool) < k:
            raise RuntimeError(f"{why}：候選只有 {len(pool)} 人，需要 {k}")
        chosen = self.rng.sample(pool, k)
        self.special.update(e["employee_id"] for e in chosen)
        return chosen

    def issue(self, type_: str, system: str, account: str, fix: str, employee_id: str | None = None, **detail):
        self.issues.append({"id": f"GT-{len(self.issues) + 1:03d}", "type": type_, "system": system,
                            "employee_id": employee_id, "account": account, "fix": fix, **detail})

    def distractor(self, type_: str, account: str, why: str, employee_id: str | None = None):
        self.distractors.append({"type": type_, "employee_id": employee_id, "account": account, "why": why})

    # ---------- HR ----------
    def employee(self, site: str, dept: str, title: str, is_manager: bool, hire: date, status: str = "active",
                 contract: bool | None = None) -> dict:
        country = ORG["sites"][site]["country"]
        p = person(self.rng, country)
        if contract is None:
            contract = (not is_manager) and (
                (dept in ("RDFW", "TEST") and self.rng.random() < 0.06) or (title == "Operator" and self.rng.random() < 0.05))
        return {"employee_id": f"{'C' if contract else 'E'}{next(self.ids)}", "legacy_id": "",
                "display": p["display"], "given": p["given"], "surname": p["surname"], "en_name": p["en_name"],
                "email": self.email(p["email_local"]), "site": site, "dept": dept, "title": title,
                "is_manager": is_manager, "manager_id": "", "hire_date": hire, "termination_date": None,
                "status": status, "employment_type": "contract" if contract else "regular", "country": country}

    def build_hr(self):
        r = self.rng
        self.active: list[dict] = []
        for site, s in ORG["sites"].items():
            for dept, n in s["headcount"].items():
                titles = [ORG["titles"][dept]["manager"]]
                for t, c in REQUIRED_TITLES.get((site, dept), {}).items():
                    titles += [t] * c
                fixed = len(titles)
                staff = ORG["titles"][dept]["staff"]
                while len(titles) < n:
                    titles.append(r.choices([t for t, _ in staff], [w for _, w in staff])[0])
                for i, title in enumerate(titles[:n]):
                    if site == "CBI":
                        hire = self.date_between(date(2026, 6, 1), date(2026, 6, 30)) if i == 0 else \
                            self.date_between(date(2026, 8, 15), date(2026, 11, 5))
                    else:
                        hire = self.date_between(date(2012, 1, 1), date(2026, 6, 30))
                    # 台北 IT 固定職稱以外的人都是約聘（特權角色情境需要約聘 IT）
                    contract = (site, dept) == ("TPE", "IT") and i >= fixed
                    self.active.append(self.employee(site, dept, title, i == 0, hire, contract=contract))

        mgr = {(e["site"], e["dept"]): e for e in self.active if e["is_manager"]}
        ceo = mgr[("TPE", "EXEC")]
        for e in self.active:
            head = mgr[(ORG["dept_home"][e["dept"]], e["dept"])]
            if e is ceo:
                continue
            if e["dept"] == "EXEC":
                e["manager_id"] = ceo["employee_id"]
            elif e["is_manager"]:
                e["manager_id"] = (ceo if e is head else head)["employee_id"]
            else:
                e["manager_id"] = mgr[(e["site"], e["dept"])]["employee_id"]
        self.mgr = mgr

        # 過去兩年離職 120 人（不含泰國新廠）
        combos = [(s, d, n) for s, v in ORG["sites"].items() if s != "CBI" for d, n in v["headcount"].items()]
        self.terminated: list[dict] = []
        for _ in range(120):
            site, dept, _n = r.choices(combos, [c[2] for c in combos])[0]
            staff = ORG["titles"][dept]["staff"]
            title = r.choices([t for t, _ in staff], [w for _, w in staff])[0]
            e = self.employee(site, dept, title, False, self.date_between(date(2012, 1, 1), date(2024, 6, 30)), "terminated")
            e["termination_date"] = self.date_between(AS_OF - timedelta(days=730), AS_OF - timedelta(days=7))
            e["manager_id"] = mgr[(site, dept)]["employee_id"]
            self.terminated.append(e)
        self.transfers: list[dict] = []

    # ---------- 情境 ----------
    def scenarios(self):
        r = self.rng
        act = self.active
        not_cbi = [e for e in act if e["site"] != "CBI"]

        # 特權角色的正常持有者先保留，避免被選進其他情境
        tpe_it = [e for e in act if e["site"] == "TPE" and e["dept"] == "IT" and e["employment_type"] == "regular"]
        sys_eng = [e for e in tpe_it if e["title"] == "System Engineer"]
        self.roles: list[tuple[str, str]] = []  # (role, email 或 break-glass 名稱)
        it_mgr = self.mgr[("TPE", "IT")]
        self.roles += [("Global Administrator", "bg-admin-01"), ("Global Administrator", "bg-admin-02"),
                       ("Global Administrator", it_mgr["email"]), ("Privileged Role Administrator", it_mgr["email"])]
        for role, e in zip(["User Administrator", "User Administrator", "Groups Administrator",
                            "Application Administrator", "Exchange Administrator"], sys_eng):
            self.roles.append((role, e["email"]))
            self.special.add(e["employee_id"])
        self.roles.append(("SharePoint Administrator", sys_eng[0]["email"]))
        for e in [e for e in tpe_it if e["title"] == "Helpdesk Engineer"]:
            self.roles.append(("Helpdesk Administrator", e["email"]))
            self.special.add(e["employee_id"])
        for site in ("TYN", "DGN", "BNH", "CBI"):
            e = self.pick([e for e in act if e["site"] == site and e["dept"] == "IT" and e["employment_type"] == "regular"],
                          1, f"{site} helpdesk")[0]
            self.roles.append(("Helpdesk Administrator", e["email"]))
        net = self.pick(tpe_it, 1, "security reader")[0]
        legal = self.pick([e for e in act if e["dept"] == "LEGAL" and e["title"] == "Compliance Specialist"], 1, "legal reader")[0]
        self.roles += [("Security Reader", net["email"]), ("Security Reader", legal["email"])]

        # ERP 職責分離的核准例外 3（干擾項），先保留人選
        self.erp_extra: dict[str, list[str]] = defaultdict(list)
        self.mitigations: list[dict] = []
        for site, title, role, rule in [("CBI", "Shipping Coordinator", "WH_INVENTORY_CTRL", "SOD-06"),
                                        ("BNH", "AP Specialist", "FIN_TREASURY", "SOD-04"),
                                        ("DGN", "Buyer", "WH_RECEIVER", "SOD-02")]:
            e = self.pick([e for e in act if e["site"] == site and e["title"] == title], 1, f"mitigation {site}")[0]
            self.erp_extra[e["employee_id"]].append(role)
            self.mitigations.append({"employee_id": e["employee_id"], "rule": rule, "role": role,
                                     "control": "人手不足，由上級主管每月覆核交易明細", "approved_by": e["manager_id"],
                                     "expires_on": date(2027, 6, 30)})
            self.distractor("sod_mitigated", e["employee_id"], f"{rule} 已核准例外並有補償控制", e["employee_id"])

        # 1. 多餘的管理員角色 5
        for cands, role, why in [
            ([e for e in act if e["dept"] == "SALES" and e["title"] == "Account Manager"], "Application Administrator",
             "業務擁有應用程式管理員"),
            ([e for e in act if e["dept"] == "FIN" and e["title"] == "Accountant"], "User Administrator", "會計擁有使用者管理員"),
            ([e for e in act if e["site"] == "DGN" and e["dept"] == "IT"], "Global Administrator", "東莞 IT 擁有全域管理員"),
            ([e for e in act if e["dept"] == "IT" and e["employment_type"] == "contract"], "Privileged Role Administrator",
             "約聘人員擁有特權角色管理員"),
            ([e for e in act if e["dept"] == "RDFW"], "Application Administrator", "韌體工程師擁有應用程式管理員"),
        ]:
            e = self.pick(cands, 1, why)[0]
            self.roles.append((role, e["email"]))
            self.issue("excess_admin", "entra", e["email"], "remove_role_assignment", e["employee_id"], role=role, note=why)

        # 1b. ERP 職責分離衝突 12（職稱特定，先選）
        sod_specs = [("Buyer", "WH_RECEIVER", "SOD-02", 1), ("Buyer", "SC_PO_APPROVER", "SOD-03", 2),
                     ("AP Specialist", "FIN_TREASURY", "SOD-04", 2), ("Vendor Master Specialist", "FIN_AP_MANAGER", "SOD-01", 1),
                     ("Order Administrator", "SD_PRICING", "SOD-07", 2), ("Shipping Coordinator", "WH_INVENTORY_CTRL", "SOD-06", 2),
                     ("Sales Operations Specialist", "FIN_AR_MANAGER", "SOD-05", 1), ("ERP Analyst", "FIN_TREASURY", "SOD-08", 1)]
        for title, role, rule, k in sod_specs:
            for e in self.pick([e for e in act if e["title"] == title and e["site"] != "CBI"], k, f"sod {rule}"):
                self.erp_extra[e["employee_id"]].append(role)
                self.issue("sod_conflict", "erp", e["employee_id"], "remove_erp_role", e["employee_id"], rule=rule, role=role)

        # 2. 離職未停用：Entra 19、GitHub 6
        fates = ["enabled"] * 19 + ["disabled"] * 46 + ["deleted"] * 55
        r.shuffle(fates)
        for e, f in zip(self.terminated, fates):
            e["entra_fate"] = f
        for e in [e for e in self.terminated if e["entra_fate"] == "enabled"]:
            self.issue("terminated_enabled", "entra", e["email"], "disable_account", e["employee_id"],
                       terminated_on=str(e["termination_date"]))
        gh_terms = r.sample([e for e in self.terminated if e["entra_fate"] != "enabled"
                             and e["dept"] in ("RDFW", "TEST", "IT", "RDHW")], 6)
        for e in gh_terms:
            e["github_after_leave"] = True

        # 3. 重新聘用 3（干擾項）：舊紀錄已離職，新紀錄在職，同一個 Email
        self.rehired_old: list[dict] = []
        for e in self.pick(not_cbi, 3, "rehire"):
            old = dict(e, employee_id=f"E{next(self.ids)}", status="terminated",
                       hire_date=self.date_between(date(2015, 1, 1), date(2020, 12, 31)),
                       termination_date=self.date_between(date(2023, 1, 1), date(2025, 6, 30)))
            e["hire_date"] = self.date_between(date(2026, 1, 5), date(2026, 6, 30))
            self.rehired_old.append(old)
            self.distractor("rehired", e["email"], "舊員工編號已離職，但同一 Email 已重新聘用，帳號屬於新紀錄", e["employee_id"])

        # 4. 約聘轉正 4（干擾項）：Entra 還留著舊的約聘編號
        for e in self.pick([e for e in not_cbi if e["dept"] in ("IT", "RDFW", "TEST", "RDHW")
                            and e["employment_type"] == "regular"], 4, "converted"):
            e["legacy_id"] = f"C{next(self.ids)}"
            e["entra_employee_id"] = e["legacy_id"]
            self.distractor("contract_converted", e["email"], "Entra 的 employeeId 是轉正前的約聘編號，HR 有對照", e["employee_id"])

        # 5. 預告離職 5（干擾項）：離職日在未來，帳號應該還開著
        for e in self.pick(not_cbi, 5, "notice"):
            e["termination_date"] = self.date_between(AS_OF + timedelta(days=5), AS_OF + timedelta(days=30))
            self.distractor("notice_period", e["email"], "離職日還沒到", e["employee_id"])

        # 6. 留職停薪 6（干擾項）：長期未登入但屬於政策例外
        for e in self.pick(not_cbi, 6, "leave"):
            e["status"] = "leave"
            e["leave_start"] = self.date_between(AS_OF - timedelta(days=220), AS_OF - timedelta(days=130))
            e["last_sign_in"] = e["leave_start"] - timedelta(days=r.randint(1, 5))
            self.distractor("leave_inactive", e["email"], "留職停薪，不適用未登入規則", e["employee_id"])

        # 7. 剛報到還沒登入 3（干擾項）
        for e in self.pick([e for e in not_cbi if e["site"] in ("TPE", "HSC")], 3, "new hire"):
            e["hire_date"] = self.date_between(AS_OF - timedelta(days=10), AS_OF - timedelta(days=2))
            e["last_sign_in"] = None
            e["never_signed_in"] = True
            self.distractor("new_account", e["email"], "帳號建立未滿 30 天", e["employee_id"])

        # 8. 轉調：永久 70（其中 30 筆舊權限沒收回、4 筆還在 30 天寬限期）
        combos = sorted({(e["site"], e["dept"]) for e in act if e["site"] != "CBI"})
        movers = self.pick([e for e in not_cbi if e["title"] != "Operator"], 70, "transfer")
        for i, e in enumerate(movers):
            same_dept = [c for c in combos if c[1] == e["dept"] and c[0] != e["site"]]
            same_site = [c for c in combos if c[0] == e["site"] and c[1] != e["dept"]]
            src = r.choice(same_dept if same_dept and (r.random() < 0.5 or not same_site) else same_site)
            if i < 4:
                eff = self.date_between(AS_OF - timedelta(days=25), AS_OF - timedelta(days=5))
            else:
                eff = self.date_between(date(2025, 5, 1), AS_OF - timedelta(days=40))
            if e["hire_date"] > eff - timedelta(days=60):
                e["hire_date"] = self.date_between(date(2014, 1, 1), eff - timedelta(days=90))
            self.transfers.append({"employee_id": e["employee_id"], "effective_date": eff, "from_site": src[0],
                                   "from_dept": src[1], "to_site": e["site"], "to_dept": e["dept"],
                                   "kind": "permanent", "end_date": None})
            old_group = f"SG-{src[0]}-{src[1]}"
            if i < 4:
                e["residual_group"] = old_group
                self.distractor("transfer_in_grace", e["email"], f"轉調 {eff} 生效，仍在寬限期內", e["employee_id"])
            elif i < 34:
                e["residual_group"] = old_group
                self.issue("transfer_residual", "entra", e["email"], "remove_group_member", e["employee_id"],
                           group=old_group, transferred_on=str(eff))

        # 9. 跨廠支援 6（干擾項）：桃園製造支援泰國新廠，到年底
        for e in self.pick([e for e in act if e["site"] == "TYN" and e["dept"] == "MFG"
                            and e["title"] in ("Process Technician", "Production Supervisor")], 6, "temp support"):
            self.transfers.append({"employee_id": e["employee_id"], "effective_date": date(2026, 10, 1), "from_site": "TYN",
                                   "from_dept": "MFG", "to_site": "CBI", "to_dept": "MFG", "kind": "temporary",
                                   "end_date": date(2026, 12, 31)})
            e["temp_group"] = "SG-CBI-MFG"
            self.distractor("temporary_assignment", e["email"], "HR 有跨廠支援紀錄，到 2026-12-31", e["employee_id"])

        # 10. 泰國新廠開站時被整批加進 TMP-CBI-Launch 18
        for e in self.pick([e for e in act if e["site"] == "CBI" and e["dept"] in ("MFG", "WH")
                            and e["title"] != "Shipping Coordinator"], 18, "cbi launch"):
            e["launch_group"] = True
            self.issue("launch_overprovisioned", "entra", e["email"], "remove_group_member", e["employee_id"],
                       group="TMP-CBI-Launch", grants=["APP-MES-TYN", "RES-Quality-Audit", "RES-RD-Designs"])

        # 11. 殭屍帳號 20（其中 3 個從未登入）
        for i, e in enumerate(self.pick(not_cbi, 20, "zombie")):
            if e["hire_date"] > AS_OF - timedelta(days=400):
                e["hire_date"] = self.date_between(date(2016, 1, 1), date(2024, 12, 31))
            if i < 3:
                e["last_sign_in"], e["never_signed_in"] = None, True
            else:
                e["last_sign_in"] = AS_OF - timedelta(days=r.randint(95, 400))
            self.issue("inactive_account", "entra", e["email"], "disable_account", e["employee_id"],
                       last_sign_in=str(e["last_sign_in"]) if e["last_sign_in"] else None)

        # 12. 同儕離群 15：從過去專案累積了一堆和同事完全不同的權限
        self.outliers = self.pick([e for e in not_cbi if e["dept"] in ("FIN", "SC", "SALES", "QA", "RDHW", "TEST", "WH")
                                   and e["title"] != "Operator"], 15, "outlier")

    # ---------- Entra ----------
    def build_entra(self):
        r = self.rng
        users, groups, members = [], {}, defaultdict(list)
        sites, depts = ORG["sites"], ORG["departments"]

        def add_group(name: str, desc: str, created: date | None = None):
            groups[name] = {"id": oid("group", name), "displayName": name, "description": desc or None,
                            "mailEnabled": False, "mailNickname": name.lower(), "securityEnabled": True, "groupTypes": [],
                            "createdDateTime": self.ts(created or self.date_between(date(2015, 1, 1), date(2025, 12, 31))),
                            "visibility": None}

        combos = sorted({(e["site"], e["dept"]) for e in self.active} | {(t["from_site"], t["from_dept"]) for t in self.transfers})
        for s, d in combos:
            add_group(f"SG-{s}-{d}", f"{sites[s]['name']} {depts[d]['zh']}")
        for s in sites:
            add_group(f"SG-{s}-AllStaff", f"{sites[s]['name']} 全體")
            for d in sites[s]["headcount"]:
                members[f"SG-{s}-AllStaff"].append(("group", f"SG-{s}-{d}"))
        for d in depts:
            add_group(f"SG-DEPT-{d}", f"{depts[d]['zh']}（全球）")
            for s, d2 in combos:
                if d2 == d:
                    members[f"SG-DEPT-{d}"].append(("group", f"SG-{s}-{d}"))
        apps = {"APP-VPN": "VPN 連線", "APP-ERP-Users": "ERP 登入", "APP-PLM": "PLM 系統", "APP-EDA-Licenses": "EDA 軟體授權",
                "APP-CRM": "CRM 系統", "APP-PowerBI-Finance": "財務 Power BI 報表", "APP-Admin-Portal": "IT 管理入口"}
        for name, desc in apps.items():
            add_group(name, desc)
        for d in ("FIN", "EXEC"):
            members["APP-PowerBI-Finance"].append(("group", f"SG-DEPT-{d}"))
        for s in ("TYN", "DGN", "BNH", "CBI"):
            add_group(f"APP-MES-{s}", f"{sites[s]['name']} MES")
            for d in ("MFG", "QA", "WH", "IT"):
                if d in sites[s]["headcount"]:
                    members[f"APP-MES-{s}"].append(("group", f"SG-{s}-{d}"))
        res_desc = {"RES-Finance-Confidential": "財務機密文件庫", "RES-Payroll": "薪資資料", "RES-HR-Records": "人事檔案",
                    "RES-Legal-Contracts": "合約文件庫", "RES-Board-Materials": "董事會資料", "RES-RD-Designs": "研發設計圖檔",
                    "RES-Customer-Pricing": "客戶報價", "RES-Quality-Audit": "品質稽核文件", "RES-Supplier-Contracts": "供應商合約"}
        for name, desc in res_desc.items():
            add_group(name, desc)
            rule = POLICY["resources"][name]
            if "sites" in rule:
                for s in rule["sites"]:
                    for d in rule["departments"]:
                        if d in sites[s]["headcount"]:
                            members[name].append(("group", f"SG-{s}-{d}"))
            else:
                for d in rule["departments"]:
                    members[name].append(("group", f"SG-DEPT-{d}"))
        add_group("TMP-CBI-Launch", "泰國新廠開站暫用（比照桃園廠範本）", date(2026, 8, 10))
        for g in ("APP-MES-TYN", "RES-Quality-Audit", "RES-RD-Designs"):
            members[g].append(("group", "TMP-CBI-Launch"))

        prj_by_dept: dict[str, list[str]] = {}
        codes = iter(r.sample(CODENAMES * 4, len(CODENAMES) * 4))
        for d, themes in PRJ_THEMES.items():
            prj_by_dept[d] = []
            for theme in themes:
                name = f"PRJ-{next(codes)}-{theme}"
                while name in groups:
                    name = f"PRJ-{next(codes)}-{theme}"
                add_group(name, "" if r.random() < 0.4 else f"{depts[d]['zh']}專案：{theme}")
                prj_by_dept[d].append(name)
        for name, desc in MISC_GROUPS:
            add_group(name, desc)
        for s in sites:
            members["DL-All-Arcwell"].append(("group", f"SG-{s}-AllStaff"))

        def base_groups(e: dict) -> list[str]:
            d, t = e["dept"], e["title"]
            gs = [f"SG-{e['site']}-{d}"]
            if t != "Operator":
                gs.append("APP-VPN")
            if self.erp_roles.get(e["employee_id"]):
                gs.append("APP-ERP-Users")
            if d in ("RDHW", "RDFW", "TEST", "QA") or t in ("Production Planner", "Production Supervisor", "Plant Manager"):
                gs.append("APP-PLM")
            if d == "RDHW":
                gs.append("APP-EDA-Licenses")
            if d in ("SALES", "FAE"):
                gs.append("APP-CRM")
            if d == "IT":
                gs.append("APP-Admin-Portal")
            if t != "Operator" and d in prj_by_dept:
                gs += r.sample(prj_by_dept[d], min(len(prj_by_dept[d]), r.choice([0, 1, 1, 2])))
            return gs

        def member_user(e: dict, enabled: bool, last: date | None, created: date, employee_id: str) -> dict:
            s = sites[e["site"]]
            u = {"id": oid("user", e["email"]), "displayName": e["display"], "givenName": e["given"], "surname": e["surname"],
                 "userPrincipalName": e["email"], "mail": e["email"], "accountEnabled": enabled, "employeeId": employee_id,
                 "employeeType": "Contractor" if e["employment_type"] == "contract" else "Employee",
                 "employeeHireDate": f"{e['hire_date']}T00:00:00Z", "department": depts[e["dept"]]["en"],
                 "jobTitle": e["title"], "officeLocation": s["en"], "companyName": ORG["company"],
                 "usageLocation": s["country"], "userType": "Member", "createdDateTime": self.ts(created),
                 "businessPhones": [], "mobilePhone": None, "preferredLanguage": None, "externalUserState": None,
                 "signInActivity": self.sign_in(last, last)}
            users.append(u)
            return u

        self.user_by_email: dict[str, dict] = {}
        for e in self.active:
            if "last_sign_in" in e:
                last = e["last_sign_in"]
            else:
                last = AS_OF - timedelta(days=r.randint(0, 25 if e["title"] == "Operator" else 14))
            created = e["hire_date"] - timedelta(days=r.randint(1, 5))
            u = member_user(e, True, last, created, e.get("entra_employee_id", e["employee_id"]))
            self.user_by_email[e["email"]] = u
            for g in base_groups(e):
                members[g].append(("user", u["id"]))
            if e.get("residual_group"):
                members[e["residual_group"]].append(("user", u["id"]))
            if e.get("temp_group"):
                members[e["temp_group"]].append(("user", u["id"]))
            if e.get("launch_group"):
                members["TMP-CBI-Launch"].append(("user", u["id"]))

        # 同儕離群：加入其他部門的 App 與專案群組
        unrestricted = ["APP-EDA-Licenses", "APP-CRM", "APP-PLM"]
        for e in self.outliers:
            u = self.user_by_email[e["email"]]
            have = {g for g, ms in members.items() if ("user", u["id"]) in ms}
            apps = [g for g in unrestricted if g not in have]
            other_prj = [g for d, gs in prj_by_dept.items() if d != e["dept"] for g in gs if g not in have]
            extra = r.sample(apps, min(2, len(apps)))
            extra += r.sample(other_prj, 6 - len(extra))
            for g in extra:
                members[g].append(("user", u["id"]))
            self.issue("peer_outlier", "entra", e["email"], "review_groups", e["employee_id"], groups=sorted(extra))

        for e in self.terminated:
            if e["entra_fate"] == "deleted":
                continue
            enabled = e["entra_fate"] == "enabled"
            last = e["termination_date"] - timedelta(days=r.randint(0, 3))
            if enabled and r.random() < 0.25:
                last = e["termination_date"] + timedelta(days=r.randint(10, 60))  # 離職後還登入過
            u = member_user(e, enabled, last, e["hire_date"] - timedelta(days=2), e["employee_id"])
            self.user_by_email[e["email"]] = u
            for g in base_groups(e):
                members[g].append(("user", u["id"]))

        # 緊急存取與服務帳號：不在 HR 名冊，由 IT 登記
        it_staff = [e for e in self.active if e["site"] == "TPE" and e["dept"] == "IT" and not e["is_manager"]]
        self.service_accounts = []
        for name, purpose, kind, interactive in [
            ("bg-admin-01", "緊急存取帳號（break-glass）", "break_glass", False),
            ("bg-admin-02", "緊急存取帳號（break-glass）", "break_glass", False),
            ("svc-mes-sync", "MES 與 ERP 工單同步", "service", False),
            ("svc-erp-integration", "ERP 介接服務", "service", False),
            ("svc-scanner-tpe", "台北掃描器寄信", "service", False),
            ("svc-backup", "雲端備份", "service", False)]:
            upn = f"{name}@{DOMAIN}"
            created = self.date_between(date(2019, 1, 1), date(2023, 12, 31))
            nonint = None if kind == "break_glass" else AS_OF - timedelta(days=r.randint(0, 2))
            u = {"id": oid("user", upn), "displayName": name, "givenName": None, "surname": None, "userPrincipalName": upn,
                 "mail": None, "accountEnabled": True, "employeeId": None, "employeeType": None, "employeeHireDate": None,
                 "department": "Information Technology" if kind == "service" else None, "jobTitle": None,
                 "officeLocation": None, "companyName": ORG["company"], "usageLocation": "TW", "userType": "Member",
                 "createdDateTime": self.ts(created), "businessPhones": [], "mobilePhone": None, "preferredLanguage": None,
                 "externalUserState": None, "signInActivity": self.sign_in(None, nonint)}
            users.append(u)
            self.user_by_email[name] = u
            owner = r.choice(it_staff)
            self.service_accounts.append({"account": upn, "kind": kind, "purpose": purpose,
                                          "owner_employee_id": owner["employee_id"], "registered_on": created})
            why = "緊急存取帳號，政策保護，不登入是正常的" if kind == "break_glass" else "已登記的服務帳號，只有非互動式登入"
            self.distractor(kind, upn, why)

        # 外部來賓 60：8 筆過期、4 筆贊助人已離職、3 筆沒有登記
        self.guest_register = []
        guest_issue_plan = ["expired"] * 8 + ["sponsor_left"] * 4 + ["unregistered"] * 3
        total = sum(c[3] for c in GUEST_COMPANIES)
        guest_issue_plan += ["ok"] * (total - len(guest_issue_plan))
        r.shuffle(guest_issue_plan)
        plan = iter(guest_issue_plan)
        ext_group = {"QA": "EXT-Auditors", "RDFW": "EXT-Firmware-Partners", "WH": "EXT-Logistics-Partners",
                     "SALES": "EXT-Customer-Portal"}
        self.guests_by_domain: dict[str, list[dict]] = defaultdict(list)
        self.guest_kind: dict[str, str] = {}
        for domain, purpose, dept, n in GUEST_COMPANIES:
            sponsors = [e for e in self.active if e["dept"] == dept]
            for _ in range(n):
                p = person(r, r.choice(["US", "DE", "JP", "TW"]))
                mail = f"{p['email_local']}@{domain}"
                while mail in self.emails:
                    mail = f"{p['email_local']}{r.randint(2, 9)}@{domain}"
                self.emails.add(mail)
                upn = f"{mail.replace('@', '_')}#EXT#@{DOMAIN}"
                created = self.date_between(date(2024, 1, 1), date(2026, 9, 30))
                kind = next(plan)
                self.guest_kind[mail] = kind
                last = AS_OF - timedelta(days=r.randint(0, 40))
                u = {"id": oid("user", upn), "displayName": f"{p['en_name']} ({domain.split('.')[0]})",
                     "givenName": p["given"], "surname": p["surname"], "userPrincipalName": upn, "mail": mail,
                     "accountEnabled": True, "employeeId": None, "employeeType": None, "employeeHireDate": None,
                     "department": None, "jobTitle": None, "officeLocation": None, "companyName": None, "usageLocation": None,
                     "userType": "Guest", "createdDateTime": self.ts(created), "businessPhones": [], "mobilePhone": None,
                     "preferredLanguage": None, "externalUserState": "Accepted" if r.random() < 0.95 else "PendingAcceptance",
                     "signInActivity": self.sign_in(last, last)}
                users.append(u)
                self.guests_by_domain[domain].append(u)
                if dept in ext_group:
                    members[ext_group[dept]].append(("user", u["id"]))
                if dept in prj_by_dept:
                    members[r.choice(prj_by_dept[dept])].append(("user", u["id"]))
                sponsor = r.choice(sponsors)
                expires = self.date_between(AS_OF + timedelta(days=20), date(2027, 12, 31))
                if kind == "expired":
                    expires = self.date_between(date(2025, 6, 1), AS_OF - timedelta(days=5))
                if kind == "sponsor_left":
                    sponsor = r.choice(self.terminated)
                if kind != "unregistered":
                    self.guest_register.append({"guest_mail": mail, "company": domain, "purpose": purpose,
                                                "sponsor_employee_id": sponsor["employee_id"], "expires_on": expires,
                                                "ticket": f"ITREQ-{r.randint(20000, 49999)}"})
                if kind != "ok":
                    self.issue("guest_access", "entra", upn, "remove_guest", reason=kind, mail=mail)

        # 目錄角色
        role_defs = [{"id": rid, "templateId": rid, "displayName": name, "isBuiltIn": True} for name, rid in ROLE_IDS.items()]
        assignments = []
        for role, who in self.roles:
            u = self.user_by_email[who]
            assignments.append({"id": oid("ra", f"{role}:{u['id']}"), "principalId": u["id"],
                                "roleDefinitionId": ROLE_IDS[role], "directoryScopeId": "/"})

        gid = {name: g["id"] for name, g in groups.items()}
        member_ids = {gid[name]: [gid[x] if k == "group" else x for k, x in ms] for name, ms in members.items()}
        self.entra = {"users": users, "groups": list(groups.values()), "members": member_ids,
                      "roleDefinitions": role_defs, "roleAssignments": assignments}

    # ---------- ERP ----------
    def build_erp_roles(self):
        self.erp_roles: dict[str, list[str]] = {}
        for e in self.active:
            roles = list(ERP_BY_TITLE.get(e["title"], []))
            if e["title"] == "Finance Manager" and e["site"] != "TPE":
                roles = ["FIN_AP_MANAGER"]
            if e["title"] == "IT Manager" and e["site"] == "TPE":
                roles = ["IT_ERP_ADMIN"]
            roles += self.erp_extra.get(e["employee_id"], [])
            if roles:
                self.erp_roles[e["employee_id"]] = roles

    # ---------- GitHub ----------
    def build_github(self):
        r = self.rng
        used_logins, used_ids = set(), set()

        def login_for(p_given: str, p_surname: str) -> str:
            g, s = ascii_fold(p_given).lower().replace("-", ""), ascii_fold(p_surname).lower()
            styles = [f"{g}{s}", f"{g[0]}{s}-arcwell", f"{g}-{s}", f"{s}{g[0]}{r.randint(1, 99)}",
                      f"{r.choice(['night', 'pixel', 'volt', 'ohm', 'byte', 'delta'])}{r.choice(['owl', 'fox', 'smith', 'dev', 'hacker'])}{r.randint(1, 999)}"]
            login = r.choice(styles)
            while login in used_logins:
                login = f"{login}{r.randint(0, 9)}"
            used_logins.add(login)
            return login

        def gh_id() -> int:
            i = r.randint(1_000_000, 200_000_000)
            while i in used_ids:
                i = r.randint(1_000_000, 200_000_000)
            used_ids.add(i)
            return i

        def profile(login: str, name: str | None, email: str | None) -> dict:
            return {"login": login, "id": gh_id(), "type": "User", "site_admin": False, "name": name, "email": email,
                    "company": None, "created_at": self.ts(self.date_between(date(2012, 1, 1), date(2024, 12, 31)))}

        def public_email(e: dict) -> str | None:
            x = r.random()
            if x < 0.25:
                return e["email"]
            if x < 0.35:
                return f"{e['email'].split('@')[0]}.dev@personal.example"
            return None

        act = self.active
        devs = [e for e in act if e["dept"] in ("RDFW", "TEST") or (e["dept"] == "IT" and e["site"] == "TPE")]
        devs += r.sample([e for e in act if e["dept"] == "RDHW"], 10)
        devs += r.sample([e for e in act if e["dept"] == "FAE"], 4)
        self.github_owner: dict[str, str | None] = {}
        members = []
        admins = {self.mgr[("TPE", "IT")]["employee_id"], self.mgr[("HSC", "RDFW")]["employee_id"]}
        for e in devs:
            p = profile(login_for(e["given"], e["surname"]), e["en_name"] if r.random() < 0.7 else None, public_email(e))
            p.update(role="admin" if e["employee_id"] in admins else "member", two_factor=True)
            members.append(p)
            self.github_owner[p["login"]] = e["employee_id"]
            e["github_login"] = p["login"]
        no2fa = self.pick([e for e in devs if e["employee_id"] not in admins], 7, "no 2fa")
        for e in no2fa:
            m = next(m for m in members if m["login"] == e["github_login"])
            m["two_factor"] = False
            self.issue("github_no_2fa", "github", m["login"], "require_2fa", e["employee_id"])
        # 沒有登記 GitHub 帳號的員工 5：帳號名稱看不出是誰，只能請人確認（其中 2 個有填姓名，可給出候選）
        unregistered = self.pick([e for e in devs if e["employee_id"] not in admins], 5, "github unregistered")
        for i, e in enumerate(unregistered):
            m = next(m for m in members if m["login"] == e["github_login"])
            del self.github_owner[m["login"]]
            new = m["login"]
            while new in used_logins:
                new = f"{r.choice(['night', 'pixel', 'volt', 'ohm', 'byte'])}{r.choice(['owl', 'fox', 'dev'])}{r.randint(1000, 9999)}"
            used_logins.add(new)
            m.update(login=new, name=e["en_name"] if i < 2 else None, email=None)
            self.github_owner[new] = e["employee_id"]
            e["github_login"], e["github_unregistered"] = new, True
            self.issue("unlinked_github", "github", new, "confirm_identity", e["employee_id"], kind="member")
        for e in [e for e in self.terminated if e.get("github_after_leave")]:
            p = profile(login_for(e["given"], e["surname"]), e["en_name"] if r.random() < 0.7 else None, None)
            p.update(role="member", two_factor=True)
            members.append(p)
            self.github_owner[p["login"]] = e["employee_id"]
            e["github_login"] = p["login"]
            self.issue("terminated_github", "github", p["login"], "remove_github_member", e["employee_id"],
                       terminated_on=str(e["termination_date"]))
        for login, name in [("fw-contractor-ray", "Ray"), ("jliu-test", None), ("pcb-helper", None),
                            ("mike-proto-2019", "Mike"), ("tempbuild-bot", None), ("summer-intern-k", None)]:
            used_logins.add(login)
            p = profile(login, name, None)
            p.update(role="member", two_factor=True)
            members.append(p)
            self.github_owner[login] = None
            self.issue("unlinked_github", "github", login, "confirm_identity", kind="member")
        r.shuffle(members)

        outside = []
        for g in r.sample(self.guests_by_domain["deltacore-fw.example"], 3):
            login = login_for(g["givenName"], g["surname"])
            p = profile(login, f"{g['givenName']} {g['surname']}", g["mail"])
            outside.append(p)
            self.github_owner[login] = f"guest:{g['mail']}"
            kind = self.guest_kind[g["mail"]]
            if kind == "unregistered":
                self.issue("unlinked_github", "github", login, "confirm_identity", kind="outside_collaborator")
            elif kind != "ok":
                self.issue("guest_github", "github", login, "remove_outside_collaborator", reason=kind, mail=g["mail"])
        for login in ("oldvendor-qa", "anon-pr-2021"):
            used_logins.add(login)
            outside.append(profile(login, None, None))
            self.github_owner[login] = None
            self.issue("unlinked_github", "github", login, "confirm_identity", kind="outside_collaborator")

        teams_spec = {"firmware": ["RDFW"], "test-automation": ["TEST"], "hw-tools": ["RDHW"], "it-infra": ["IT"],
                      "fae-tools": ["FAE"], "mes-integration": ["IT", "TEST"], "platform": ["RDFW", "IT"],
                      "docs": ["RDFW", "RDHW", "FAE"], "security": ["IT"], "web": ["IT"], "data": ["TEST", "IT"],
                      "release": ["RDFW"]}
        dept_of = {e["employee_id"]: e["dept"] for e in self.active + self.terminated}
        teams, team_members = [], {}
        for i, (slug, ds) in enumerate(teams_spec.items()):
            teams.append({"id": 9000 + i, "slug": slug, "name": slug.replace("-", " ").title(), "privacy": "closed"})
            pool = [m["login"] for m in members if dept_of.get(self.github_owner[m["login"]]) in ds]
            team_members[slug] = sorted(r.sample(pool, max(1, int(len(pool) * r.uniform(0.4, 0.9)))))
        # IT 維護的 GitHub 帳號登記表：員工自己登記、IT 確認過的對應
        self.github_links = [{"login": e["github_login"], "employee_id": e["employee_id"],
                              "confirmed_on": self.date_between(date(2022, 1, 1), min(AS_OF, e["termination_date"] or AS_OF))}
                             for e in self.active + self.terminated
                             if e.get("github_login") and not e.get("github_unregistered")]
        self.github = {"org": GITHUB_ORG, "members": members, "outside_collaborators": outside,
                       "teams": teams, "team_members": team_members}

    # ---------- 輸出 ----------
    def run(self) -> dict:
        self.build_hr()
        self.scenarios()
        self.build_erp_roles()
        self.build_entra()
        self.build_github()
        return {
            "hr": self.active + self.terminated + self.rehired_old, "transfers": self.transfers,
            "entra": self.entra, "github": self.github,
            "erp": {"roles": [{"code": c, "name": n, "transactions": t} for c, (n, t) in ERP_ROLES.items()],
                    "assignments": [{"user_id": u, "role": ro} for u, rs in sorted(self.erp_roles.items()) for ro in rs]},
            "mitigations": self.mitigations, "guest_register": self.guest_register,
            "service_accounts": self.service_accounts, "github_links": self.github_links,
            "ground_truth": {"as_of": str(AS_OF), "issues": self.issues, "distractors": self.distractors},
        }


HR_FIELDS = ["employee_id", "legacy_id", "display", "en_name", "email", "site", "dept", "title", "manager_id",
             "hire_date", "termination_date", "status", "employment_type"]


def write_csv(path: Path, rows: list[dict], fields: list[str]):
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        for row in rows:
            w.writerow({k: "" if row.get(k) is None else row.get(k) for k in fields})


def write(world: dict, out: Path = OUT) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "hr_employees.csv", sorted(world["hr"], key=lambda e: e["employee_id"]), HR_FIELDS)
    write_csv(out / "hr_transfers.csv", world["transfers"],
              ["employee_id", "effective_date", "from_site", "from_dept", "to_site", "to_dept", "kind", "end_date"])
    write_csv(out / "sod_mitigations.csv", world["mitigations"],
              ["employee_id", "rule", "role", "control", "approved_by", "expires_on"])
    write_csv(out / "guest_register.csv", world["guest_register"],
              ["guest_mail", "company", "purpose", "sponsor_employee_id", "expires_on", "ticket"])
    write_csv(out / "github_links.csv", world["github_links"], ["login", "employee_id", "confirmed_on"])
    write_csv(out / "service_accounts.csv", world["service_accounts"],
              ["account", "kind", "purpose", "owner_employee_id", "registered_on"])
    for name in ("entra", "github", "erp", "ground_truth"):
        (out / f"{name}.json").write_text(json.dumps(world[name], ensure_ascii=False, indent=1, default=str))
    hr = world["hr"]
    manifest = {
        "seed": SEED, "as_of": str(AS_OF),
        "hr": dict(Counter(e["status"] for e in hr)), "hr_active_like": sum(e["status"] != "terminated" for e in hr),
        "transfers": dict(Counter(t["kind"] for t in world["transfers"])),
        "entra_users": dict(Counter(u["userType"] for u in world["entra"]["users"])),
        "entra_groups": len(world["entra"]["groups"]), "entra_role_assignments": len(world["entra"]["roleAssignments"]),
        "github_members": len(world["github"]["members"]),
        "github_outside_collaborators": len(world["github"]["outside_collaborators"]),
        "erp_assignments": len(world["erp"]["assignments"]),
        "issues": dict(Counter(i["type"] for i in world["ground_truth"]["issues"])),
        "issues_total": len(world["ground_truth"]["issues"]),
        "distractors": dict(Counter(d["type"] for d in world["ground_truth"]["distractors"])),
        "distractors_total": len(world["ground_truth"]["distractors"]),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=1))
    return manifest


def main():
    manifest = write(Gen(SEED).run())
    print(json.dumps(manifest, ensure_ascii=False, indent=1))


if __name__ == "__main__":
    main()
