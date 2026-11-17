"""覆核流程

Revision ID: 0001
"""

import sqlalchemy as sa
from alembic import op

revision = "0001"
down_revision = None


def upgrade() -> None:
    op.create_table(
        "campaigns",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("as_of", sa.Date, nullable=False),
        sa.Column("snapshot_path", sa.String(500), nullable=False),
        sa.Column("created_by", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("direct", sa.JSON, nullable=False),
        sa.Column("suppressed", sa.Integer, nullable=False),
        sa.Column("ledger_path", sa.String(500), nullable=True),
    )
    op.create_table(
        "review_items",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("rule", sa.String(40), nullable=False),
        sa.Column("system", sa.String(20), nullable=False),
        sa.Column("account", sa.String(200), nullable=False),
        sa.Column("fix", sa.String(40), nullable=False),
        sa.Column("object", sa.String(200), nullable=False),
        sa.Column("subject_id", sa.String(20), nullable=True),
        sa.Column("finding", sa.JSON, nullable=False),
        sa.Column("explanation", sa.Text, nullable=False),
        sa.Column("reviewer_id", sa.String(20), nullable=False),
        sa.Column("original_reviewer_id", sa.String(20), nullable=False),
        sa.Column("level", sa.Integer, nullable=False),
        sa.Column("due_at", sa.DateTime, nullable=False),
        sa.Column("reminded_at", sa.DateTime, nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("decision", sa.String(20), nullable=True),
        sa.Column("decision_detail", sa.JSON, nullable=False),
        sa.Column("reason", sa.Text, nullable=True),
        sa.Column("decided_by", sa.String(20), nullable=True),
        sa.Column("decided_at", sa.DateTime, nullable=True),
        sa.UniqueConstraint("campaign_id", "rule", "account", "fix", "object"),
    )
    op.create_index("ix_review_items_campaign_id", "review_items", ["campaign_id"])
    op.create_index("ix_review_items_reviewer_id", "review_items", ["reviewer_id"])
    op.create_table(
        "review_exceptions",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("rule", sa.String(40), nullable=False),
        sa.Column("account", sa.String(200), nullable=False),
        sa.Column("object", sa.String(200), nullable=False),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("approved_by", sa.String(20), nullable=False),
        sa.Column("expires_on", sa.Date, nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("review_items.id"), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_review_exceptions_account", "review_exceptions", ["account"])
    op.create_table(
        "events",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("item_id", sa.Integer, sa.ForeignKey("review_items.id"), nullable=True),
        sa.Column("at", sa.DateTime, nullable=False),
        sa.Column("actor", sa.String(40), nullable=False),
        sa.Column("event", sa.String(40), nullable=False),
        sa.Column("detail", sa.JSON, nullable=False),
    )
    op.create_index("ix_events_campaign_id", "events", ["campaign_id"])
    op.create_table(
        "mails",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("campaign_id", sa.Integer, sa.ForeignKey("campaigns.id"), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("to", sa.String(200), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("item_ids", sa.JSON, nullable=False),
        sa.Column("sent_at", sa.DateTime, nullable=False),
    )
    op.create_index("ix_mails_campaign_id", "mails", ["campaign_id"])


def downgrade() -> None:
    for t in ("mails", "events", "review_exceptions", "review_items", "campaigns"):
        op.drop_table(t)
