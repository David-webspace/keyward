"""規則提案的生命週期：建立（含驗證與影響預覽）→ IT 套用或捨棄 → 已套用的可以撤回。"""

from datetime import date, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai import ORG_GROUP, Draft, label_group
from app.identity import Directory
from app.internal import Internal
from app.llm import LLM
from app.models import Proposal
from app.review import ReviewError
from app.rules import Vocabulary, apply, effective, impact, validate
from app.seed.generate import ORG

DEPT_ZH = {k: v["zh"] for k, v in ORG["departments"].items()}
SITE_ZH = {k: v["name"] for k, v in ORG["sites"].items()}
HAS_EFFECT = {"resource", "sod", "setting"}


def vocab_for(snapshot: dict, internal: Internal) -> Vocabulary:
    return Vocabulary({g["displayName"]: g.get("description") for g in snapshot["entra"]["groups"]}, DEPT_ZH, SITE_ZH,
                      set().union(*internal.erp_roles.values()))


def has_effect(p: Proposal) -> bool:
    return p.kind in HAS_EFFECT or (p.kind == "group_label" and p.proposal.get("sensitivity") == "restricted")


def preview(db: Session, p: Proposal, snapshot: dict, internal: Internal, as_of: date) -> dict | None:
    if p.errors or not has_effect(p):
        return None
    before = effective(db)
    names = {e["employee_id"]: e["display"] for e in internal.hr}
    return impact(snapshot, internal, as_of, before, apply(before, p), names)


def create(db: Session, draft: Draft, source: str, prompt: str, target: str, actor: str, snapshot: dict,
           internal: Internal, as_of: date, now: datetime) -> Proposal:
    status = "clarify" if draft.kind == "clarify" else "invalid" if draft.errors else "proposed"
    p = Proposal(source=source, kind=draft.kind, prompt=prompt, target=target, proposal=draft.proposal,
                 rationale=draft.rationale, evidence=draft.evidence, errors=draft.errors, model=draft.model,
                 elapsed_ms=draft.elapsed_ms, status=status, created_by=actor, created_at=now)
    db.add(p)
    db.flush()  # 取得 id：職責分離規則的代號用它
    p.impact = preview(db, p, snapshot, internal, as_of) if status == "proposed" else None
    db.commit()
    return p


def unlabeled_groups(db: Session, snapshot: dict) -> list[str]:
    """還沒有規則、也還沒有提案的群組（組織群組與部門彙總群組不需要標註）。"""
    covered = set(effective(db)["resources"])
    pending = set(db.scalars(select(Proposal.target).where(Proposal.source == "classifier",
                                                           Proposal.status != "reverted")))
    return sorted(g["displayName"] for g in snapshot["entra"]["groups"]
                  if g["displayName"] not in covered | pending and not ORG_GROUP.match(g["displayName"])
                  and not g["displayName"].startswith("SG-DEPT-"))


def suggest_groups(db: Session, llm: LLM, limit: int, actor: str, snapshot: dict, internal: Internal, as_of: date,
                   now: datetime) -> list[Proposal]:
    ident, vocab = Directory(internal), vocab_for(snapshot, internal)
    out = []
    for name in unlabeled_groups(db, snapshot)[:limit]:
        draft = label_group(llm, name, snapshot, ident, vocab)
        out.append(create(db, draft, "classifier", name, name, actor, snapshot, internal, as_of, now))
    return out


def get(db: Session, pid: int) -> Proposal:
    p = db.get(Proposal, pid)
    if p is None:
        raise ReviewError(404, "找不到這個提案")
    return p


def decide(db: Session, pid: int, actor: str, action: str, now: datetime, snapshot: dict, internal: Internal,
           as_of: date, edits: dict | None = None) -> Proposal:
    p = get(db, pid)
    if action == "revert":
        if p.status != "applied":
            raise ReviewError(409, "只有已套用的提案可以撤回")
        p.status = "reverted"
    elif p.status not in ("proposed", "invalid"):
        raise ReviewError(409, "這個提案已經處理過了")
    elif action == "reject":
        p.status = "rejected"
    else:
        if edits is not None:
            # IT 修改後再套用：重新驗證、重新預覽，保留模型原始建議在 evidence 旁邊供稽核
            p.proposal = edits | {"group": p.proposal.get("group")} if p.kind == "group_label" else edits
            p.errors = validate(p.kind, p.proposal, vocab_for(snapshot, internal))
            p.status = "invalid" if p.errors else "proposed"
            p.impact = preview(db, p, snapshot, internal, as_of)
        if p.status != "proposed":
            raise ReviewError(422, "提案沒有通過驗證：" + "；".join(p.errors))
        p.status = "applied"
    p.decided_by, p.decided_at = actor, now
    db.commit()
    return p


FIELDS = ("id", "source", "kind", "prompt", "target", "proposal", "rationale", "evidence", "errors", "impact", "model",
          "elapsed_ms", "status", "created_by", "created_at", "decided_by", "decided_at")


def view(p: Proposal) -> dict:
    return {c: getattr(p, c) for c in FIELDS}
