"""規則疊加與影響預覽。

生效的規則 = policy.yaml ＋ 依核准順序疊加的提案（群組標註為限制級、資源存取對象、職責分離、門檻）。
撤回一條提案，就是把它從疊加清單拿掉，policy.yaml 本身永遠不被程式改寫。
"""

import copy
from dataclasses import dataclass
from datetime import date

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.findings import POLICY, evaluate
from app.internal import Internal
from app.models import Proposal

SETTINGS = {"inactivity_days": (14, 365), "new_account_grace_days": (1, 90), "transfer_grace_days": (0, 90)}


@dataclass
class Vocabulary:
    """驗證用的合法值：全部來自實際資料，模型提到不存在的東西就擋下。"""
    groups: dict[str, str | None]      # 群組名稱 → 說明
    departments: dict[str, str]        # 代碼 → 中文
    sites: dict[str, str]
    transactions: set[str]


def apply(policy: dict, p: Proposal) -> dict:
    out = copy.deepcopy(policy)
    x = p.proposal
    if p.kind == "group_label" and x["sensitivity"] == "restricted":
        out["resources"][x["group"]] = audience(x["audience"])
    elif p.kind == "resource":
        out["resources"][x["group"]] = audience(x)
    elif p.kind == "sod":
        out["sod_rules"][f"SOD-P{p.id}"] = {"left": x["left"], "right": x["right"], "zh": x["zh"]}
    elif p.kind == "setting":
        out[x["key"]] = x["value"]
    return out


def audience(x: dict) -> dict:
    rule = {"departments": sorted(x["departments"])}
    if x.get("sites"):
        rule["sites"] = sorted(x["sites"])
    return rule


def effective(db: Session, base: dict = POLICY) -> dict:
    policy = copy.deepcopy(base)
    for p in db.scalars(select(Proposal).where(Proposal.status == "applied").order_by(Proposal.decided_at, Proposal.id)):
        policy = apply(policy, p)
    return policy


def validate(kind: str, x: dict, vocab: Vocabulary) -> list[str]:
    errs = []

    def check_audience(aud: dict):
        for d in aud.get("departments") or []:
            if d not in vocab.departments:
                errs.append(f"部門代碼 {d} 不存在")
        for s in aud.get("sites") or []:
            if s not in vocab.sites:
                errs.append(f"據點代碼 {s} 不存在")
        if not aud.get("departments"):
            errs.append("沒有指定可以存取的部門")

    if kind in ("group_label", "resource"):
        if x.get("group") not in vocab.groups:
            errs.append(f"找不到群組「{x.get('group')}」")
    if kind == "group_label":
        if x.get("sensitivity") not in ("restricted", "internal", "general"):
            errs.append("敏感度只能是 restricted、internal、general")
        if x.get("owner_dept") not in vocab.departments:
            errs.append(f"擁有部門 {x.get('owner_dept')} 不存在")
        if x.get("sensitivity") == "restricted":
            check_audience(x.get("audience") or {})
            if x.get("owner_dept") not in (x.get("audience") or {}).get("departments", []):
                errs.append("限制級群組的存取對象必須包含擁有部門")
    elif kind == "resource":
        check_audience(x)
    elif kind == "sod":
        for side in ("left", "right"):
            if x.get(side) not in vocab.transactions:
                errs.append(f"交易代碼 {x.get(side)} 不存在")
        if x.get("left") == x.get("right"):
            errs.append("職責分離的兩邊不能是同一個交易")
    elif kind == "setting":
        lo_hi = SETTINGS.get(x.get("key"))
        if lo_hi is None:
            errs.append(f"不能用這個方式修改 {x.get('key')}")
        elif not isinstance(x.get("value"), int) or not lo_hi[0] <= x["value"] <= lo_hi[1]:
            errs.append(f"{x.get('key')} 必須是 {lo_hi[0]} 到 {lo_hi[1]} 之間的整數")
    return errs


def impact(snapshot: dict, internal: Internal, as_of: date, before: dict, after: dict, names: dict[str, str]) -> dict:
    """同一份快照，分別用套用前、套用後的規則跑一次發現，列出差異。"""
    def keyed(policy):
        return {(f.rule, f.account, f.fix, f.object): f for f in evaluate(snapshot, internal, as_of, policy)}

    old, new = keyed(before), keyed(after)

    def rows(keys, src):
        return [{"rule": k[0], "account": k[1], "object": k[3],
                 "name": names.get(src[k].employee_id) if src[k].employee_id else None} for k in sorted(keys)]

    added, removed = new.keys() - old.keys(), old.keys() - new.keys()
    return {"added": len(added), "removed": len(removed), "added_rows": rows(added, new)[:50],
            "removed_rows": rows(removed, old)[:50]}
