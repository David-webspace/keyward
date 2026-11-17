"""規則變更提案

Revision ID: 0002
"""

import sqlalchemy as sa
from alembic import op

revision = "0002"
down_revision = "0001"


def upgrade() -> None:
    op.create_table(
        "policy_proposals",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("prompt", sa.Text, nullable=False),
        sa.Column("target", sa.String(200), nullable=False),
        sa.Column("proposal", sa.JSON, nullable=False),
        sa.Column("rationale", sa.Text, nullable=True),
        sa.Column("evidence", sa.JSON, nullable=False),
        sa.Column("errors", sa.JSON, nullable=False),
        sa.Column("impact", sa.JSON, nullable=True),
        sa.Column("model", sa.String(100), nullable=True),
        sa.Column("elapsed_ms", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("created_by", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime, nullable=False),
        sa.Column("decided_by", sa.String(20), nullable=True),
        sa.Column("decided_at", sa.DateTime, nullable=True),
    )
    op.create_index("ix_policy_proposals_target", "policy_proposals", ["target"])


def downgrade() -> None:
    op.drop_table("policy_proposals")
