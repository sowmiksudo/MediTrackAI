"""live_docs_module

Revision ID: 0002
Revises: 0001
Create Date: 2026-11-20 23:32:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "users",
        sa.Column("role", sa.String(length=32), nullable=False, server_default="user"),
    )

    op.create_table(
        "live_docs_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("visibility_mode", sa.String(length=24), nullable=False, server_default="force_on"),
        sa.Column("publish_start_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("publish_end_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_hours", sa.Integer(), nullable=True),
        sa.Column("team_name", sa.String(length=160), nullable=False, server_default="Team MediTrackAI"),
        sa.Column("active_version_tag", sa.String(length=48), nullable=False, server_default="v1.0.0"),
        sa.Column("updated_by", sa.String(length=255), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "live_docs_sections",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("category", sa.String(length=24), nullable=False, server_default="technical"),
        sa.Column("section_code", sa.String(length=16), nullable=True),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column("subtitle", sa.String(length=300), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_visible", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("content_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("draft_markdown", sa.Text(), nullable=False, server_default=""),
        sa.Column("mermaid_diagram", sa.Text(), nullable=True),
        sa.Column("draft_mermaid", sa.Text(), nullable=True),
        sa.Column("has_unpublished_changes", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_live_docs_sections_id"), "live_docs_sections", ["id"], unique=False)
    op.create_index(op.f("ix_live_docs_sections_slug"), "live_docs_sections", ["slug"], unique=True)
    op.create_index(op.f("ix_live_docs_sections_sort_order"), "live_docs_sections", ["sort_order"], unique=False)

    op.create_table(
        "live_docs_team_members",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("full_name", sa.String(length=160), nullable=False),
        sa.Column("role_title", sa.String(length=160), nullable=False),
        sa.Column("email", sa.String(length=255), nullable=False),
        sa.Column("avatar_url", sa.Text(), nullable=True),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_live_docs_team_members_id"), "live_docs_team_members", ["id"], unique=False)

    op.create_table(
        "live_docs_versions",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("version_tag", sa.String(length=48), nullable=False),
        sa.Column("summary", sa.String(length=300), nullable=False),
        sa.Column("snapshot_json", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("published_by", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_live_docs_versions_id"), "live_docs_versions", ["id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_live_docs_versions_id"), table_name="live_docs_versions")
    op.drop_table("live_docs_versions")
    op.drop_index(op.f("ix_live_docs_team_members_id"), table_name="live_docs_team_members")
    op.drop_table("live_docs_team_members")
    op.drop_index(op.f("ix_live_docs_sections_sort_order"), table_name="live_docs_sections")
    op.drop_index(op.f("ix_live_docs_sections_slug"), table_name="live_docs_sections")
    op.drop_index(op.f("ix_live_docs_sections_id"), table_name="live_docs_sections")
    op.drop_table("live_docs_sections")
    op.drop_table("live_docs_settings")
    op.drop_column("users", "role")
