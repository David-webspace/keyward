"""覆核流程的資料表。時間一律存 UTC（不帶時區）。"""

from datetime import UTC, date, datetime

from sqlalchemy import JSON, Date, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


def utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class Base(DeclarativeBase):
    pass


class Campaign(Base):
    __tablename__ = "campaigns"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(200))
    as_of: Mapped[date] = mapped_column(Date)
    snapshot_path: Mapped[str] = mapped_column(String(500))
    created_by: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    status: Mapped[str] = mapped_column(String(20), default="open")
    direct: Mapped[list] = mapped_column(JSON, default=list)       # 不需覆核、直接交付執行的發現（例如已離職）
    suppressed: Mapped[int] = mapped_column(Integer, default=0)    # 因為已核准的例外而沒有列入的發現數
    ledger_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ReviewItem(Base):
    __tablename__ = "review_items"
    __table_args__ = (UniqueConstraint("campaign_id", "rule", "account", "fix", "object"),)
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    rule: Mapped[str] = mapped_column(String(40))
    system: Mapped[str] = mapped_column(String(20))
    account: Mapped[str] = mapped_column(String(200))
    fix: Mapped[str] = mapped_column(String(40))
    object: Mapped[str] = mapped_column(String(200), default="")
    subject_id: Mapped[str | None] = mapped_column(String(20), nullable=True)   # 被覆核的人（HR 員工編號）
    finding: Mapped[dict] = mapped_column(JSON)
    explanation: Mapped[str] = mapped_column(Text)
    reviewer_id: Mapped[str] = mapped_column(String(20), index=True)             # 目前負責的覆核者
    original_reviewer_id: Mapped[str] = mapped_column(String(20))
    level: Mapped[int] = mapped_column(Integer, default=0)                       # 升級了幾次
    due_at: Mapped[datetime] = mapped_column(DateTime)
    reminded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")           # pending / decided / overdue
    decision: Mapped[str | None] = mapped_column(String(20), nullable=True)      # keep / revoke / partial
    decision_detail: Mapped[dict] = mapped_column(JSON, default=dict)
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    decided_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class ReviewException(Base):
    """主管決定保留的項目：到期前同一個發現不再列出。"""
    __tablename__ = "review_exceptions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    rule: Mapped[str] = mapped_column(String(40))
    account: Mapped[str] = mapped_column(String(200), index=True)
    object: Mapped[str] = mapped_column(String(200), default="")
    reason: Mapped[str] = mapped_column(Text)
    approved_by: Mapped[str] = mapped_column(String(20))
    expires_on: Mapped[date] = mapped_column(Date)
    item_id: Mapped[int] = mapped_column(ForeignKey("review_items.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)


class Event(Base):
    """稽核軌跡：誰在什麼時候做了什麼。只新增，不修改。"""
    __tablename__ = "events"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    item_id: Mapped[int | None] = mapped_column(ForeignKey("review_items.id"), nullable=True)
    at: Mapped[datetime] = mapped_column(DateTime)
    actor: Mapped[str] = mapped_column(String(40))
    event: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)


class Mail(Base):
    """寄出的通知信（同時寄到 SMTP，這裡留底）。"""
    __tablename__ = "mails"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    campaign_id: Mapped[int] = mapped_column(ForeignKey("campaigns.id"), index=True)
    kind: Mapped[str] = mapped_column(String(20))      # assigned / reminder / escalated / handed_off
    to: Mapped[str] = mapped_column(String(200))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    item_ids: Mapped[list] = mapped_column(JSON, default=list)
    sent_at: Mapped[datetime] = mapped_column(DateTime)


class Proposal(Base):
    """規則變更提案：AI 群組標註、一句話寫規則。經程式驗證與影響預覽，IT 核准後才疊加到 policy.yaml 上生效。"""
    __tablename__ = "policy_proposals"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    source: Mapped[str] = mapped_column(String(20))        # classifier / sentence
    kind: Mapped[str] = mapped_column(String(20))          # group_label / resource / sod / setting / clarify
    prompt: Mapped[str] = mapped_column(Text)              # 原始的一句話，或被標註的群組名稱
    target: Mapped[str] = mapped_column(String(200), default="", index=True)
    proposal: Mapped[dict] = mapped_column(JSON, default=dict)
    rationale: Mapped[str | None] = mapped_column(Text, nullable=True)
    evidence: Mapped[list] = mapped_column(JSON, default=list)
    errors: Mapped[list] = mapped_column(JSON, default=list)
    impact: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    model: Mapped[str | None] = mapped_column(String(100), nullable=True)
    elapsed_ms: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))        # proposed / invalid / clarify / applied / rejected / reverted
    created_by: Mapped[str] = mapped_column(String(20))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow)
    decided_by: Mapped[str | None] = mapped_column(String(20), nullable=True)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
