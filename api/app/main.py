"""覆核 API。

登入：AUTH_MODE=demo 時從 HR 名冊選一位在職員工登入（只供本機示範，正式環境改用 Entra ID SSO）。
權限：一般員工只看得到指派給自己的項目；IT 管理者可以建立活動、看全部進度、交付執行，但不能代替主管做決定。
"""

import json
from collections import Counter
from contextlib import asynccontextmanager
from datetime import UTC, date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

import jwt
from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import evidence, people, proposals
from app.ai import draft_rule
from app.config import Settings, get_settings
from app.db import get_db
from app.execute import Ledger
from app.findings import evaluate
from app.internal import load
from app.llm import LLM, make_llm, not_configured
from app.mailer import Mailer
from app.models import Campaign, Proposal, ReviewItem, utcnow
from app.review import (
    RULE_ZH,
    Org,
    ReviewError,
    active_exceptions,
    apply_exceptions,
    create_campaign,
    decide,
    hand_off,
    progress,
    tick,
    visible_item,
)
from app.rules import effective

COOKIE = "keyward_session"


@lru_cache
def org() -> Org:
    return Org(load(get_settings().data_dir / "synthetic"))


def mailer(s: Settings = Depends(get_settings)) -> Mailer:
    return Mailer(s.smtp_host, s.smtp_port, s.mail_from, s.allowed_recipient_suffix, s.web_base_url)


def current_user(request: Request, s: Settings = Depends(get_settings)) -> str:
    token = request.cookies.get(COOKIE)
    if not token:
        raise HTTPException(401, "請先登入")
    try:
        emp = jwt.decode(token, s.jwt_secret, algorithms=["HS256"])["sub"]
    except jwt.PyJWTError:
        raise HTTPException(401, "請重新登入")
    if org().active(emp) is None:  # 登入後才離職：token 還沒過期也一律擋下
        raise HTTPException(401, "請重新登入")
    return emp


def admin_user(emp: str = Depends(current_user)) -> str:
    if emp not in org().admins:
        raise HTTPException(403, "需要 IT 管理者權限")
    return emp


@asynccontextmanager
async def lifespan(_: FastAPI):
    s = get_settings()
    if s.auth_mode not in ("demo", "entra"):
        raise RuntimeError("AUTH_MODE 只能是 demo 或 entra")
    yield


app = FastAPI(title="keyward", lifespan=lifespan, docs_url=None, redoc_url=None, openapi_url=None)


@app.exception_handler(ReviewError)
async def review_error(_: Request, exc: ReviewError):
    return JSONResponse({"detail": str(exc)}, exc.status)


@app.get("/health")
def health():
    return {"ok": True}


class DemoLogin(BaseModel):
    employee_id: str = Field(max_length=20)


@app.post("/auth/demo-login")
def demo_login(body: DemoLogin, response: Response, s: Settings = Depends(get_settings)):
    if s.auth_mode != "demo":
        raise HTTPException(404, "Not Found")
    person = org().active(body.employee_id)
    if person is None:
        raise HTTPException(401, "找不到這位在職員工")
    now = datetime.now(UTC)
    token = jwt.encode({"sub": body.employee_id, "iat": now, "exp": now + timedelta(hours=s.jwt_ttl_hours)},
                       s.jwt_secret, algorithm="HS256")
    response.set_cookie(COOKIE, token, httponly=True, samesite="lax", secure=s.cookie_secure,
                        max_age=s.jwt_ttl_hours * 3600)
    return me(body.employee_id)


@app.post("/auth/logout")
def logout(response: Response):
    response.delete_cookie(COOKIE)
    return {"ok": True}


@app.get("/demo/accounts")
def demo_accounts(s: Settings = Depends(get_settings), db: Session = Depends(get_db)):
    """示範模式的建議登入身分：資安負責人、目前待辦最多的幾位覆核者、一位沒有任何待辦的員工。"""
    if s.auth_mode != "demo":
        raise HTTPException(404, "Not Found")
    o = org()
    rows = db.execute(select(ReviewItem.reviewer_id, ReviewItem.rule).where(ReviewItem.status == "pending")).all()
    load_by = Counter(r[0] for r in rows)
    rules: dict[str, set[str]] = {}
    for emp, rule in rows:
        rules.setdefault(emp, set()).add(RULE_ZH[rule])

    def card(emp: str, role: str) -> dict:
        p = o.ident.by_id[emp]
        return {"employee_id": emp, "name": p["display"], "title": p["title"], "site": p["site"], "role": role,
                "pending": load_by.get(emp, 0), "rules": sorted(rules.get(emp, []))[:3]}

    out = [card(o.security, "資安負責人・IT 管理者")]
    for emp, _ in load_by.most_common(6):
        if emp != o.security and len(out) < 4:
            out.append(card(emp, "主管"))
    idle = next((e for e in sorted(o.people) if e not in load_by and o.people[e]["dept"] != "IT"), None)
    if idle:
        out.append(card(idle, "一般員工（沒有待辦）"))
    return out


def latest_snapshot(s: Settings) -> tuple[Path, dict]:
    snaps = sorted((s.data_dir / "state" / "snapshots").glob("*.json"))
    if not snaps:
        raise HTTPException(409, "還沒有同步快照，請先執行同步")
    return snaps[-1], json.loads(snaps[-1].read_text())


@app.get("/me")
def me(emp: str = Depends(current_user)):
    p = org().ident.by_id[emp]
    return {"employee_id": emp, "name": p["display"], "title": p["title"], "site": p["site"], "dept": p["dept"],
            "is_admin": emp in org().admins}


class NewCampaign(BaseModel):
    name: str = Field(min_length=2, max_length=200)
    as_of: date | None = None


@app.post("/campaigns")
def new_campaign(body: NewCampaign, emp: str = Depends(admin_user), db: Session = Depends(get_db),
                 m: Mailer = Depends(mailer), s: Settings = Depends(get_settings)):
    path, snapshot = latest_snapshot(s)
    as_of = body.as_of or date.today()
    findings = evaluate(snapshot, org().internal, as_of, effective(db))
    c = create_campaign(db, body.name, snapshot, str(path), findings, org(), m, as_of, utcnow(), emp)
    return {"id": c.id, **progress(db, c.id), "direct": len(c.direct), "suppressed": c.suppressed}


@app.get("/campaigns")
def campaigns(_: str = Depends(admin_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Campaign).order_by(Campaign.id.desc())).all()
    return [{"id": c.id, "name": c.name, "status": c.status, "as_of": c.as_of, "created_at": c.created_at,
             **progress(db, c.id)} for c in rows]


def get_campaign(db: Session, cid: int) -> Campaign:
    c = db.get(Campaign, cid)
    if c is None:
        raise HTTPException(404, "找不到這個活動")
    return c


@app.get("/campaigns/{cid}")
def campaign(cid: int, _: str = Depends(admin_user), db: Session = Depends(get_db)):
    c = get_campaign(db, cid)
    items = db.scalars(select(ReviewItem).where(ReviewItem.campaign_id == cid)).all()
    by_rule: dict[str, Counter] = {}
    for i in items:
        by_rule.setdefault(i.rule, Counter())[i.decision or i.status] += 1
    reviewers = Counter(i.reviewer_id for i in items if i.status != "decided")
    execution = None
    if c.ledger_path and Path(c.ledger_path).exists():
        execution = dict(Counter(a.status for a in Ledger(Path(c.ledger_path)).actions.values()))
    return {"id": c.id, "name": c.name, "status": c.status, "as_of": c.as_of, "created_at": c.created_at,
            "direct": len(c.direct), "suppressed": c.suppressed, "ledger": c.ledger_path, "execution": execution,
            "by_rule": [{"rule": r, "label": RULE_ZH[r], **cnt} for r, cnt in sorted(by_rule.items())],
            "waiting_on": [{"employee_id": e, "name": org().name(e), "open": n} for e, n in reviewers.most_common(8)],
            **progress(db, cid)}


@app.get("/campaigns/{cid}/items")
def campaign_items(cid: int, status: str | None = None, rule: str | None = None, _: str = Depends(admin_user),
                   db: Session = Depends(get_db)):
    get_campaign(db, cid)
    q = select(ReviewItem).where(ReviewItem.campaign_id == cid)
    if status:
        q = q.where(ReviewItem.status == status)
    if rule:
        q = q.where(ReviewItem.rule == rule)
    return [item_view(i) for i in db.scalars(q.order_by(ReviewItem.id).limit(500))]


@app.get("/campaigns/{cid}/evidence")
def campaign_evidence(cid: int, _: str = Depends(admin_user), db: Session = Depends(get_db)):
    get_campaign(db, cid)
    policy_text = (Path(__file__).with_name("policy.yaml")).read_text()
    name, data = evidence.build(db, cid, org(), policy_text)
    return Response(data, media_type="application/zip", headers={"content-disposition": f'attachment; filename="{name}"'})


@app.get("/findings")
def findings(as_of: date | None = None, _: str = Depends(admin_user), db: Session = Depends(get_db),
             s: Settings = Depends(get_settings)):
    path, snapshot = latest_snapshot(s)
    day = as_of or date.today()
    raw = evaluate(snapshot, org().internal, day, effective(db))
    kept, suppressed = apply_exceptions(raw, active_exceptions(db, day))
    o = org()
    return {"snapshot": path.name, "taken_at": snapshot["taken_at"], "as_of": day, "suppressed": suppressed,
            "items": [{"rule": f.rule, "label": RULE_ZH[f.rule], "system": f.system,
                       "account": f.account, "object": f.object, "fix": f.fix, "employee_id": f.employee_id,
                       "name": o.ident.by_id[f.employee_id]["display"] if f.employee_id in o.ident.by_id else None,
                       "confirmed": f.confirmed} for f in kept]}


@app.get("/people")
def search_people(q: str = "", _: str = Depends(admin_user)):
    q = q.strip().lower()[:50]
    if not q:
        return []
    o = org()
    hits = [e for e in o.ident.by_email.values()
            if q in e["employee_id"].lower() or q in e["email"].lower() or q in e["display"].lower() or q in e["en_name"].lower()]
    return [{"employee_id": e["employee_id"], "name": e["display"], "title": e["title"], "site": e["site"],
             "dept": e["dept"], "status": e["status"]} for e in hits[:20]]


@app.get("/people/{emp}")
def person(emp: str, as_of: date | None = None, _: str = Depends(admin_user), s: Settings = Depends(get_settings),
           db: Session = Depends(get_db)):
    _, snapshot = latest_snapshot(s)
    o = org()
    result = people.profile(emp, snapshot, o.ident, evaluate(snapshot, o.internal, as_of or date.today(), effective(db)))
    if result is None:
        raise HTTPException(404, "找不到這位員工")
    return result


class Tick(BaseModel):
    now: datetime | None = None  # 只在示範模式接受，用來展示提醒與升級


@app.post("/campaigns/{cid}/tick")
def run_tick(cid: int, body: Tick, _: str = Depends(admin_user), db: Session = Depends(get_db),
             m: Mailer = Depends(mailer), s: Settings = Depends(get_settings)):
    get_campaign(db, cid)
    if body.now and s.auth_mode != "demo":
        raise HTTPException(422, "只有示範模式可以指定時間")
    now = body.now.replace(tzinfo=None) if body.now else utcnow()
    return tick(db, cid, org(), m, now)


@app.post("/campaigns/{cid}/hand-off")
def run_hand_off(cid: int, emp: str = Depends(admin_user), db: Session = Depends(get_db),
                 s: Settings = Depends(get_settings)):
    c = get_campaign(db, cid)
    snapshot = json.loads(Path(c.snapshot_path).read_text())
    ledger = hand_off(db, cid, emp, org(), snapshot, s.data_dir / "state" / "executions", utcnow())
    return {"ledger": str(ledger.path), "actions": len(ledger.actions),
            "approved": sum(a.status == "approved" for a in ledger.actions.values()),
            "awaiting_it": sum(a.status == "planned" for a in ledger.actions.values()), "manual": len(ledger.meta["manual"])}


def item_view(it: ReviewItem) -> dict:
    o = org()
    return {"id": it.id, "campaign_id": it.campaign_id, "rule": it.rule, "label": RULE_ZH[it.rule], "system": it.system,
            "account": it.account, "object": it.object, "subject_id": it.subject_id,
            "subject_name": o.name(it.subject_id) if it.subject_id else None,
            "reviewer_id": it.reviewer_id, "reviewer_name": o.name(it.reviewer_id),
            "explanation": it.explanation, "groups": it.finding["evidence"].get("groups") if it.rule == "peer_outlier" else None,
            "status": it.status, "due_at": it.due_at, "level": it.level, "decision": it.decision, "reason": it.reason,
            "decision_detail": it.decision_detail, "decided_at": it.decided_at}


@app.get("/reviews")
def my_reviews(status: str = "pending", emp: str = Depends(current_user), db: Session = Depends(get_db)):
    items = db.scalars(select(ReviewItem).where(ReviewItem.reviewer_id == emp, ReviewItem.status == status)
                       .order_by(ReviewItem.due_at, ReviewItem.id)).all()
    return [item_view(i) for i in items]


@app.get("/reviews/{item_id}")
def review(item_id: int, emp: str = Depends(current_user), db: Session = Depends(get_db)):
    return item_view(visible_item(db, item_id, emp, org()))


class Decision(BaseModel):
    decision: str | None = Field(default=None, max_length=10)
    reason: str | None = Field(default=None, max_length=2000)
    keep_until: date | None = None
    groups: dict[str, str] | None = Field(default=None, max_length=50)


@app.post("/reviews/{item_id}/decision")
def make_decision(item_id: int, body: Decision, emp: str = Depends(current_user), db: Session = Depends(get_db)):
    it = decide(db, item_id, emp, org(), utcnow(), body.decision, body.reason, body.keep_until, body.groups)
    return item_view(it)


# ---------- 規則提案（AI 群組標註、一句話寫規則） ----------

def get_llm(s: Settings = Depends(get_settings)) -> LLM:
    msg = not_configured(s)
    if msg:
        raise HTTPException(503, msg)
    return make_llm(s)


@app.get("/policy")
def policy(_: str = Depends(admin_user), db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    _, snapshot = latest_snapshot(s)
    rows = db.scalars(select(Proposal).order_by(Proposal.id.desc()).limit(300)).all()
    return {"ai_message": not_configured(s), "model": s.llm_model,
            "unlabeled": len(proposals.unlabeled_groups(db, snapshot)), "proposals": [proposals.view(p) for p in rows]}


class Sentence(BaseModel):
    text: str = Field(min_length=4, max_length=300)
    as_of: date | None = None


@app.post("/policy/drafts")
def new_draft(body: Sentence, emp: str = Depends(admin_user), db: Session = Depends(get_db),
              s: Settings = Depends(get_settings), llm: LLM = Depends(get_llm)):
    _, snapshot = latest_snapshot(s)
    internal = org().internal
    draft = draft_rule(llm, body.text.strip(), proposals.vocab_for(snapshot, internal))
    p = proposals.create(db, draft, "sentence", body.text.strip(), draft.proposal.get("group") or draft.proposal.get("key")
                         or "", emp, snapshot, internal, body.as_of or date.today(), utcnow())
    return proposals.view(p)


class Suggest(BaseModel):
    limit: int = Field(default=5, ge=1, le=20)  # 每次最多標註 20 個群組，避免單一請求跑太久、模型費用失控
    as_of: date | None = None


@app.post("/policy/groups/suggest")
def suggest(body: Suggest, emp: str = Depends(admin_user), db: Session = Depends(get_db),
            s: Settings = Depends(get_settings), llm: LLM = Depends(get_llm)):
    _, snapshot = latest_snapshot(s)
    made = proposals.suggest_groups(db, llm, body.limit, emp, snapshot, org().internal, body.as_of or date.today(), utcnow())
    return {"made": [proposals.view(p) for p in made], "remaining": len(proposals.unlabeled_groups(db, snapshot))}


class ProposalAction(BaseModel):
    edits: dict | None = None
    as_of: date | None = None


@app.post("/policy/proposals/{pid}/{action}")
def proposal_action(pid: int, action: str, body: ProposalAction, emp: str = Depends(admin_user),
                    db: Session = Depends(get_db), s: Settings = Depends(get_settings)):
    if action not in ("apply", "reject", "revert"):
        raise HTTPException(404, "Not Found")
    _, snapshot = latest_snapshot(s)
    p = proposals.decide(db, pid, emp, action, utcnow(), snapshot, org().internal, body.as_of or date.today(), body.edits)
    return proposals.view(p)
