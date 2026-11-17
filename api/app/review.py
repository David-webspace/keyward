"""覆核流程：建立活動 → 分派 → 決定 → 提醒與升級 → 交付執行。

分派規則（覆核者一律是 HR 名冊上的在職員工，且不能是被覆核的本人）：
- 轉調未收回、敏感資源、殭屍帳號、同儕離群、職責分離 → 當事人的主管
- 來賓 → 贊助人；贊助人已離職 → 贊助人原本的主管；沒有登記 → 資安負責人
- 多餘的管理員、GitHub 身分不明、未開 2FA → 資安負責人
- 已離職（HR 名冊即依據）→ 不需覆核，直接列入交付執行，由 IT 核准

逾期不會自動撤銷：升級給上一層主管，到最上層仍未決定就標成逾期交給資安處理，避免誤停權。
"""

from collections import defaultdict
from dataclasses import asdict
from datetime import date, datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.execute import IRREVERSIBLE, Ledger, plan
from app.findings import POLICY, Finding
from app.identity import Directory
from app.internal import Internal
from app.mailer import Mailer
from app.models import Campaign, Event, Mail, ReviewException, ReviewItem

BY_MANAGER = {"transfer_residual", "resource_access", "inactive_account", "peer_outlier", "sod_conflict"}
BY_SPONSOR = {"guest_access", "guest_github", "guest_resource"}
BY_SECURITY = {"excess_admin", "unlinked_github", "github_no_2fa"}
DIRECT = {"terminated_enabled", "terminated_github"}
RULE_ZH = {"transfer_residual": "轉調後舊單位權限未收回", "resource_access": "可存取不符資格的敏感資源",
           "inactive_account": "長期未登入", "peer_outlier": "權限明顯多於同部門同職稱的同事",
           "sod_conflict": "ERP 職責分離衝突", "guest_access": "外部來賓存取有問題", "guest_github": "外部來賓仍有 GitHub 權限",
           "excess_admin": "不符資格的管理員角色", "unlinked_github": "無法確認是誰的 GitHub 帳號",
           "github_no_2fa": "GitHub 未開兩步驟驗證", "terminated_enabled": "已離職帳號仍啟用",
           "terminated_github": "已離職仍在 GitHub 組織", "guest_resource": "外部來賓可存取限制資源"}


class ReviewError(Exception):
    def __init__(self, status: int, message: str):
        super().__init__(message)
        self.status = status


class Org:
    """HR 名冊上的主管關係與角色。"""

    def __init__(self, internal: Internal, policy: dict = POLICY):
        self.ident = Directory(internal)
        self.internal = internal
        self.people = {e["employee_id"]: e for e in internal.hr if e["status"] != "terminated"}
        cfg = policy["review"]
        so = cfg["security_owner"]
        self.security = next(e["employee_id"] for e in self.people.values()
                             if (e["site"], e["dept"], e["title"]) == (so["site"], so["dept"], so["title"]))
        a = cfg["admins"]
        self.admins = {e["employee_id"] for e in self.people.values()
                       if e["site"] == a["site"] and e["dept"] == a["dept"] and e["title"] in a["titles"]}

    def active(self, emp_id: str | None) -> dict | None:
        return self.people.get(emp_id) if emp_id else None

    def manager_of(self, emp_id: str, exclude: str | None = None) -> str:
        """往上找第一個在職、且不是被覆核者本人的主管；找不到就交給資安負責人。"""
        seen = set()
        cur = self.ident.by_id.get(emp_id)
        while cur and cur["manager_id"] and cur["manager_id"] not in seen:
            seen.add(cur["manager_id"])
            boss = self.ident.by_id.get(cur["manager_id"])
            if boss and self.active(boss["employee_id"]) and boss["employee_id"] != exclude:
                return boss["employee_id"]
            cur = boss
        return self.security

    def reviewer_for(self, f: Finding) -> str:
        if f.rule in BY_MANAGER:
            return self.manager_of(f.employee_id, exclude=f.employee_id)
        if f.rule in BY_SPONSOR:
            mail = (f.evidence.get("register") or {}).get("guest_mail") or f.evidence.get("guest")
            reg = self.internal.guest_register.get((mail or "").lower())
            if reg is None:
                return self.security
            if self.active(reg["sponsor_employee_id"]):
                return reg["sponsor_employee_id"]
            return self.manager_of(reg["sponsor_employee_id"])
        return self.security

    def name(self, emp_id: str) -> str:
        e = self.ident.by_id.get(emp_id)
        return f"{e['display']}（{e['title']}）" if e else emp_id


def explain(f: Finding, org: Org, group_desc: dict[str, str]) -> str:
    """給覆核者看的白話說明。內容全部來自發現的依據與群組說明，不經過模型。"""
    who = org.name(f.employee_id) if f.employee_id else f.account
    ev = f.evidence

    def grants(names: list[str]) -> str:
        return "、".join(f"{g}（{group_desc[g]}）" if group_desc.get(g) else g for g in names)

    if f.rule == "transfer_residual":
        t = ev.get("transfer") or {}
        s = f"{who} 已於 {t.get('effective_date', '（無轉調紀錄）')} 轉調到 {ev['current']}，但仍是舊單位群組 {f.object} 的成員"
        return s + (f"，因此還能存取 {grants(ev['grants'])}。" if ev.get("grants") else "。")
    if f.rule == "resource_access":
        return f"{who} 現職是 {ev['current']}，因為是 {f.object} 的成員，可以存取 {grants(ev['grants'])}，不符合這些資源的資格。"
    if f.rule == "inactive_account":
        last = ev.get("last_sign_in") or "從未登入"
        return f"{who} 的帳號仍啟用，但最後一次登入是 {last}，超過 {POLICY['inactivity_days']} 天。"
    if f.rule == "peer_outlier":
        cohort = "同部門同職稱" if ev.get("cohort") == "title" else "同部門（同職稱的人太少，改用整個部門比較）"
        return (f"和 {ev['peers']} 位{cohort}的同事相比，{who} 多了下列幾乎沒有人有的群組，請逐一決定是否保留："
                f"{grants(ev['groups'])}。")
    if f.rule == "sod_conflict":
        return f"{who} 在 ERP 同時擁有 {ev['conflict']} 的權限（角色：{'、'.join(ev['roles'])}）。保留必須說明補償控制。"
    if f.rule == "guest_resource":
        return (f"外部來賓 {ev.get('guest') or f.account} 因為是 {f.object} 的成員，可以存取 {grants(ev['grants'])}。"
                "來賓不應存取限制資源，除非規則明確允許。")
    if f.rule in BY_SPONSOR:
        reason = {"expired": "登記已過期", "sponsor_left": "贊助人已離職", "unregistered": "沒有任何登記"}[ev["reason"]]
        target = "GitHub 外部協作者權限" if f.rule == "guest_github" else "公司帳號"
        guest = f.account.split("#EXT#")[0].rsplit("_", 1)
        shown = "@".join(guest) if "#EXT#" in f.account and len(guest) == 2 else f.account
        return f"外部來賓 {shown} 的{target}仍有效，但{reason}。保留請填新的到期日。"
    if f.rule == "excess_admin":
        return f"{who} 擔任 {f.object}，但不符合這個角色的資格（{ev.get('holder') or '非員工帳號'}）。"
    if f.rule == "unlinked_github":
        s = ev.get("suggestion")
        hint = f"系統推測可能是 {s['name']}（{s['employee_id']}，{s['status']}），需要確認。" if s else "找不到任何線索。"
        return f"GitHub 帳號 {f.account} 沒有在 IT 登記表上，{hint}"
    return f"{who} 的 GitHub 帳號 {f.account} 尚未開啟兩步驟驗證。"


def key(f) -> tuple:
    return (f.rule, f.account, f.object)


def active_exceptions(db: Session, as_of: date) -> dict[tuple, ReviewException]:
    rows = db.scalars(select(ReviewException).where(ReviewException.expires_on >= as_of))
    return {(x.rule, x.account, x.object): x for x in rows}


def apply_exceptions(findings: list[Finding], exceptions: dict[tuple, ReviewException]) -> tuple[list[Finding], int]:
    """拿掉已核准保留的發現；同儕離群逐個群組比對。"""
    out, suppressed = [], 0
    for f in findings:
        if f.rule == "peer_outlier":
            keep = [g for g in f.evidence["groups"] if (f.rule, f.account, g) not in exceptions]
            if len(keep) < len(f.evidence["groups"]):
                suppressed += 1
                if not keep:
                    continue
                f = Finding(**(asdict(f) | {"evidence": f.evidence | {"groups": keep}}))
        elif key(f) in exceptions:
            suppressed += 1
            continue
        out.append(f)
    return out, suppressed


def log(db: Session, campaign_id: int, at: datetime, actor: str, event: str, item_id: int | None = None, **detail):
    db.add(Event(campaign_id=campaign_id, item_id=item_id, at=at, actor=actor, event=event, detail=detail))


# ---------- 建立活動 ----------

def create_campaign(db: Session, name: str, snapshot: dict, snapshot_path: str, findings: list[Finding], org: Org,
                    mailer: Mailer, as_of: date, now: datetime, created_by: str) -> Campaign:
    if created_by not in org.admins:
        raise ReviewError(403, "只有 IT 管理者可以建立覆核活動")
    findings, suppressed = apply_exceptions(findings, active_exceptions(db, as_of))
    c = Campaign(name=name, as_of=as_of, snapshot_path=snapshot_path, created_by=created_by, created_at=now,
                 direct=[asdict(f) for f in findings if f.rule in DIRECT], suppressed=suppressed)
    db.add(c)
    db.flush()
    group_desc = {g["displayName"]: g.get("description") for g in snapshot["entra"]["groups"]}
    due = now + timedelta(days=POLICY["review"]["due_days"])
    for f in findings:
        if f.rule in DIRECT:
            continue
        reviewer = org.reviewer_for(f)
        db.add(ReviewItem(campaign_id=c.id, rule=f.rule, system=f.system, account=f.account, fix=f.fix, object=f.object,
                          subject_id=f.employee_id, finding=asdict(f), explanation=explain(f, org, group_desc),
                          reviewer_id=reviewer, original_reviewer_id=reviewer, level=0, due_at=due, status="pending",
                          decision_detail={}))
    db.flush()
    log(db, c.id, now, created_by, "campaign_created", findings=len(findings), direct=len(c.direct), suppressed=suppressed)
    items = db.scalars(select(ReviewItem).where(ReviewItem.campaign_id == c.id)).all()
    notify(db, c, org, mailer, now, "assigned", items)
    db.commit()
    return c


def notify(db: Session, c: Campaign, org: Org, mailer: Mailer, now: datetime, kind: str, items: list[ReviewItem]):
    """同一個覆核者的項目彙整成一封信。"""
    by_reviewer: dict[str, list[ReviewItem]] = defaultdict(list)
    for it in items:
        by_reviewer[it.reviewer_id].append(it)
    title = {"assigned": "請在期限內完成權限覆核", "reminder": "提醒：權限覆核即將到期",
             "escalated": "權限覆核已逾期，轉交給您決定", "overdue": "權限覆核已逾期，請資安處理"}[kind]
    for reviewer, its in by_reviewer.items():
        person = org.ident.by_id[reviewer]
        due = min(i.due_at for i in its).strftime("%Y-%m-%d")
        lines = [f"{person['display']} 您好：", "", f"「{c.name}」有 {len(its)} 個項目需要您決定，期限 {due}。", ""]
        lines += [f"- {RULE_ZH[i.rule]}：{i.account}" + (f"（{i.object}）" if i.object else "") for i in its[:20]]
        if len(its) > 20:
            lines.append(f"- 另外還有 {len(its) - 20} 項")
        lines += ["", f"前往覆核：{mailer.web_base_url}/reviews"]
        mailer.send(person["email"], f"[keyward] {title}（{len(its)} 項）", "\n".join(lines))
        db.add(Mail(campaign_id=c.id, kind=kind, to=person["email"], subject=f"[keyward] {title}（{len(its)} 項）",
                    body="\n".join(lines), item_ids=[i.id for i in its], sent_at=now))


# ---------- 決定 ----------

def visible_item(db: Session, item_id: int, viewer: str, org: Org) -> ReviewItem:
    """覆核者只能看到指派給自己的項目；不存在與無權限一律回 404，避免透露項目存在。"""
    q = select(ReviewItem).where(ReviewItem.id == item_id)
    if viewer not in org.admins:
        q = q.where(ReviewItem.reviewer_id == viewer)
    it = db.scalar(q)
    if it is None:
        raise ReviewError(404, "找不到這個項目")
    return it


def decide(db: Session, item_id: int, actor: str, org: Org, now: datetime, decision: str, reason: str | None = None,
           keep_until: date | None = None, groups: dict[str, str] | None = None) -> ReviewItem:
    # 擁有權寫在查詢條件裡：只有目前的覆核者查得到，連 IT 管理者也不能代替主管決定
    it = db.scalar(select(ReviewItem).where(ReviewItem.id == item_id, ReviewItem.reviewer_id == actor))
    if it is None:
        raise ReviewError(404, "找不到這個項目")
    if it.status == "decided":
        raise ReviewError(409, "這個項目已經決定過了")
    if db.get(Campaign, it.campaign_id).status == "handed_off":
        raise ReviewError(409, "這個活動已經交付執行，不能再改決定")
    cfg = POLICY["review"]
    reason = (reason or "").strip()
    today = now.date()

    if it.rule == "peer_outlier":
        listed = set(it.finding["evidence"]["groups"])
        if not groups or set(groups) != listed or not set(groups.values()) <= {"keep", "revoke"}:
            raise ReviewError(422, "請對每一個群組選擇保留或撤銷")
        kept = sorted(g for g, d in groups.items() if d == "keep")
        decision = "keep" if len(kept) == len(listed) else "revoke" if not kept else "partial"
    elif decision not in ("keep", "revoke"):
        raise ReviewError(422, "決定只能是保留或撤銷")
    else:
        kept = [it.object] if decision == "keep" else []

    if kept:
        if len(reason) < 5:
            raise ReviewError(422, "保留必須說明理由（至少 5 個字）")
        if it.rule in BY_SPONSOR and keep_until is None:
            raise ReviewError(422, "保留外部來賓必須填新的到期日")
        keep_until = keep_until or today + timedelta(days=cfg["default_keep_days"])
        if not today < keep_until <= today + timedelta(days=cfg["max_keep_days"]):
            raise ReviewError(422, f"保留期限必須在今天之後、{cfg['max_keep_days']} 天以內")
        for obj in kept:
            db.add(ReviewException(rule=it.rule, account=it.account, object=obj, reason=reason, approved_by=actor,
                                   expires_on=keep_until, item_id=it.id, created_at=now))

    it.status, it.decision, it.reason, it.decided_by, it.decided_at = "decided", decision, reason or None, actor, now
    it.decision_detail = {"groups": groups} if groups else {}
    if keep_until and kept:
        it.decision_detail = it.decision_detail | {"keep_until": keep_until.isoformat()}
    log(db, it.campaign_id, now, actor, "decided", it.id, decision=decision, reason=reason or None,
        keep_until=keep_until.isoformat() if kept else None)
    db.commit()
    return it


# ---------- 提醒與升級 ----------

def tick(db: Session, campaign_id: int, org: Org, mailer: Mailer, now: datetime) -> dict:
    c = db.get(Campaign, campaign_id)
    cfg = POLICY["review"]
    pending = db.scalars(select(ReviewItem).where(ReviewItem.campaign_id == campaign_id,
                                                  ReviewItem.status == "pending")).all()
    remind, escalated, overdue = [], [], []
    for it in pending:
        if now >= it.due_at:
            nxt = org.manager_of(it.reviewer_id, exclude=it.subject_id)
            if it.reviewer_id == org.security or nxt == it.reviewer_id:
                it.status = "overdue"
                overdue.append(it)
                log(db, c.id, now, "system", "overdue", it.id, reviewer=it.reviewer_id)
                continue
            log(db, c.id, now, "system", "escalated", it.id, frm=it.reviewer_id, to=nxt)
            it.reviewer_id, it.level = nxt, it.level + 1
            it.due_at, it.reminded_at = now + timedelta(days=cfg["escalation_days"]), None
            escalated.append(it)
        elif it.reminded_at is None and now >= it.due_at - timedelta(days=cfg["remind_before_days"]):
            it.reminded_at = now
            remind.append(it)
    notify(db, c, org, mailer, now, "reminder", remind)
    notify(db, c, org, mailer, now, "escalated", escalated)
    notify(db, c, org, mailer, now, "overdue", overdue)
    db.commit()
    return {"reminded": len(remind), "escalated": len(escalated), "overdue": len(overdue)}


def progress(db: Session, campaign_id: int) -> dict:
    items = db.scalars(select(ReviewItem).where(ReviewItem.campaign_id == campaign_id)).all()
    out: dict = {"total": len(items), "by_status": defaultdict(int), "by_decision": defaultdict(int),
                 "escalated": sum(i.level > 0 for i in items)}
    for i in items:
        out["by_status"][i.status] += 1
        if i.decision:
            out["by_decision"][i.decision] += 1
    return out


# ---------- 交付執行 ----------

def hand_off(db: Session, campaign_id: int, actor: str, org: Org, snapshot: dict, exec_dir, now: datetime) -> Ledger:
    """把決定撤銷的項目與「已離職」直接項目轉成執行計畫。

    主管撤銷的動作在帳本裡記為已核准（核准者是那位主管）；已離職的與不可逆的動作留給 IT 另外核准。
    """
    if actor not in org.admins:
        raise ReviewError(403, "只有 IT 管理者可以交付執行")
    c = db.get(Campaign, campaign_id)
    if c.ledger_path:
        raise ReviewError(409, "這個活動已經交付過執行")
    approver: dict[tuple, ReviewItem] = {}
    findings = [Finding(**f) for f in c.direct]
    items = db.scalars(select(ReviewItem).where(ReviewItem.campaign_id == campaign_id,
                                                ReviewItem.decision.in_(("revoke", "partial")))).all()
    for it in items:
        f = Finding(**it.finding)
        if it.rule == "peer_outlier":
            for g, d in it.decision_detail["groups"].items():
                if d == "revoke":
                    approver[("remove_group_member", f.account, g)] = it
                    findings.append(Finding("peer_outlier", f.system, f.account, "remove_group_member", g,
                                            f.employee_id, True, {"reviewed_in": it.id}))
        else:
            if f.fix in ("confirm_identity", "require_2fa"):
                # 決定撤銷 = 移除這個 GitHub 帳號（身分確認後無人認領，或拒絕開 2FA）
                fix = f.evidence.get("removal_fix", "remove_github_member")
                f = Finding(**(asdict(f) | {"fix": fix, "confirmed": True}))
            approver[(f.fix, f.account, f.object)] = it
            findings.append(f)
    p = plan(findings, snapshot)
    ledger = Ledger.create(exec_dir / f"campaign-{campaign_id}-{p['id']}.json", p | {"campaign_id": campaign_id})
    for a in ledger.actions.values():
        it = approver.get((a.fix, a.account, a.object))
        if it is None or a.irreversible:
            a.log("awaiting_it_approval", reason=IRREVERSIBLE.get(a.fix, "已離職：依 HR 名冊直接處理，需 IT 核准"))
            continue
        a.approval = {"by": it.decided_by, "at": it.decided_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
                      "fingerprint": a.fingerprint(), "via": "review", "item_id": it.id}
        a.status = "approved"
        a.log("approved", by=it.decided_by, via=f"review item {it.id}")
    ledger.save()
    c.ledger_path, c.status = str(ledger.path), "handed_off"
    log(db, c.id, now, actor, "handed_off", ledger=str(ledger.path), actions=len(ledger.actions),
        approved=sum(a.status == "approved" for a in ledger.actions.values()))
    db.commit()
    return ledger
