"""稽核證據包：一個活動從建立、分派、決定、升級、例外到執行結果的完整紀錄，打包成 zip（CSV＋摘要）。"""

import csv
import hashlib
import io
import json
import zipfile
from collections import Counter
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.execute import Ledger
from app.models import Campaign, Event, Mail, ReviewException, ReviewItem
from app.review import RULE_ZH, Org


def _csv(rows: list[dict], fields: list[str]) -> str:
    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fields, extrasaction="ignore")
    w.writeheader()
    for r in rows:
        w.writerow({k: "" if r.get(k) is None else r[k] for k in fields})
    return "﻿" + buf.getvalue()  # BOM：Excel 開中文才不會亂碼


def build(db: Session, cid: int, org: Org, policy_text: str) -> tuple[str, bytes]:
    c = db.get(Campaign, cid)
    items = db.scalars(select(ReviewItem).where(ReviewItem.campaign_id == cid).order_by(ReviewItem.id)).all()
    ids = [i.id for i in items]
    events = db.scalars(select(Event).where(Event.campaign_id == cid).order_by(Event.id)).all()
    mails = db.scalars(select(Mail).where(Mail.campaign_id == cid).order_by(Mail.id)).all()
    exceptions = db.scalars(select(ReviewException).where(ReviewException.item_id.in_(ids))).all() if ids else []

    def who(emp: str | None) -> str:
        return org.name(emp) if emp else ""

    item_rows = [{"id": i.id, "rule": RULE_ZH.get(i.rule, i.rule), "account": i.account, "object": i.object,
                  "subject": who(i.subject_id), "reviewer": who(i.reviewer_id), "original_reviewer": who(i.original_reviewer_id),
                  "escalations": i.level, "status": i.status, "decision": i.decision, "reason": i.reason,
                  "decided_by": who(i.decided_by), "decided_at": i.decided_at, "keep_until": i.decision_detail.get("keep_until"),
                  "explanation": i.explanation} for i in items]
    execution = []
    if c.ledger_path and Path(c.ledger_path).exists():
        for a in Ledger(Path(c.ledger_path)).actions.values():
            execution.append({"action_id": a.id, "fix": a.fix, "account": a.account, "object": a.object, "status": a.status,
                              "approved_by": who((a.approval or {}).get("by")) or (a.approval or {}).get("by"),
                              "approved_via": (a.approval or {}).get("via"),
                              "events": " → ".join(h["event"] for h in a.history)})
    policy_hash = hashlib.sha256(policy_text.encode()).hexdigest()[:16]
    decisions = Counter(i.decision or i.status for i in items)
    summary = "\n".join([
        f"# 稽核證據包：{c.name}", "",
        f"- 活動編號：{c.id}；資料基準日：{c.as_of}；建立者：{who(c.created_by)}；建立時間（UTC）：{c.created_at:%Y-%m-%d %H:%M}",
        f"- 同步快照：{Path(c.snapshot_path).name}",
        f"- 規則檔 policy.yaml 指紋：{policy_hash}（同一份規則產生的證據包指紋相同）",
        f"- 覆核項目 {len(items)} 項；結果：" + "、".join(f"{k} {v}" for k, v in sorted(decisions.items())),
        f"- 不需覆核、依 HR 名冊直接處理：{len(c.direct)} 項；因既有例外未列入：{c.suppressed} 項",
        f"- 寄出通知 {len(mails)} 封；升級 {sum(i.level > 0 for i in items)} 項",
        f"- 執行帳本：{Path(c.ledger_path).name if c.ledger_path else '尚未交付執行'}",
        "", "## 檔案", "",
        "- items.csv：每個覆核項目、覆核者（含升級前）、決定、理由、說明文字",
        "- exceptions.csv：決定保留而建立的例外與到期日",
        "- events.csv：依時間排列的完整事件紀錄",
        "- mails.csv：寄出的通知信", "- direct.csv：不需覆核的項目",
        "- execution.csv：交付執行後每個動作的狀態與核准來源", "- policy.yaml：當時使用的規則",
    ]) + "\n"
    files = {
        "summary.md": summary,
        "items.csv": _csv(item_rows, list(item_rows[0]) if item_rows else ["id"]),
        "exceptions.csv": _csv([{"rule": x.rule, "account": x.account, "object": x.object, "reason": x.reason,
                                 "approved_by": who(x.approved_by), "expires_on": x.expires_on, "item_id": x.item_id}
                                for x in exceptions], ["rule", "account", "object", "reason", "approved_by", "expires_on", "item_id"]),
        "events.csv": _csv([{"at": e.at, "actor": who(e.actor) if e.actor in org.ident.by_id else e.actor, "event": e.event,
                             "item_id": e.item_id, "detail": json.dumps(e.detail, ensure_ascii=False)} for e in events],
                           ["at", "actor", "event", "item_id", "detail"]),
        "mails.csv": _csv([{"sent_at": m.sent_at, "kind": m.kind, "to": m.to, "subject": m.subject, "items": len(m.item_ids)}
                           for m in mails], ["sent_at", "kind", "to", "subject", "items"]),
        "direct.csv": _csv([{"rule": d["rule"], "account": d["account"], "fix": d["fix"]} for d in c.direct],
                           ["rule", "account", "fix"]),
        "execution.csv": _csv(execution, ["action_id", "fix", "account", "object", "status", "approved_by",
                                          "approved_via", "events"]),
        "policy.yaml": policy_text,
    }
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for name, text in files.items():
            z.writestr(name, text)
    return f"keyward-evidence-campaign-{c.id}.zip", buf.getvalue()
