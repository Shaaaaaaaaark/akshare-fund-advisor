"""Initial transactional, evidence and document schema.

Revision ID: 20260727_0001
Revises:
Create Date: 2026-07-27
"""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects.postgresql import JSONB

revision = "20260727_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    postgresql = bind.dialect.name == "postgresql"
    if postgresql:
        op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    json_type = JSONB() if postgresql else sa.JSON()
    vector_type = Vector(1024) if postgresql else sa.JSON()

    op.create_table(
        "conversations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "tasks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "conversation_id",
            sa.String(36),
            sa.ForeignKey("conversations.id"),
            nullable=False,
        ),
        sa.Column("trace_id", sa.String(64), nullable=False),
        sa.Column("query", sa.Text(), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("state", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_tasks_conversation_id", "tasks", ["conversation_id"])
    op.create_index("ix_tasks_trace_id", "tasks", ["trace_id"])
    op.create_index("ix_tasks_status", "tasks", ["status"])

    op.create_table(
        "evidence_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id"),
            nullable=False,
        ),
        sa.Column("evidence_type", sa.String(32), nullable=False),
        sa.Column("subject_type", sa.String(64), nullable=False),
        sa.Column("subject_id", sa.String(128), nullable=False),
        sa.Column("field", sa.String(255), nullable=False),
        sa.Column("payload", json_type, nullable=False),
    )
    op.create_index("ix_evidence_records_task_id", "evidence_records", ["task_id"])
    op.create_index(
        "ix_evidence_records_evidence_type",
        "evidence_records",
        ["evidence_type"],
    )
    op.create_index(
        "ix_evidence_subject_field",
        "evidence_records",
        ["subject_id", "field"],
    )
    op.create_index(
        "ix_evidence_records_subject_type",
        "evidence_records",
        ["subject_type"],
    )
    op.create_index(
        "ix_evidence_records_subject_id",
        "evidence_records",
        ["subject_id"],
    )
    op.create_index("ix_evidence_records_field", "evidence_records", ["field"])

    op.create_table(
        "claim_records",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id"),
            nullable=False,
        ),
        sa.Column("claim_type", sa.String(32), nullable=False),
        sa.Column("allowed", sa.Boolean(), nullable=False),
        sa.Column("payload", json_type, nullable=False),
    )
    op.create_index("ix_claim_records_task_id", "claim_records", ["task_id"])
    op.create_index(
        "ix_claim_records_claim_type",
        "claim_records",
        ["claim_type"],
    )

    op.create_table(
        "reports",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "task_id",
            sa.String(36),
            sa.ForeignKey("tasks.id"),
            nullable=False,
            unique=True,
        ),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("evidence_grade", sa.String(1), nullable=False),
        sa.Column("payload", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_reports_task_id", "reports", ["task_id"], unique=True)
    op.create_index("ix_reports_status", "reports", ["status"])
    op.create_index(
        "ix_reports_evidence_grade",
        "reports",
        ["evidence_grade"],
    )

    op.create_table(
        "user_state",
        sa.Column("user_id", sa.String(64), primary_key=True),
        sa.Column("risk_profile", json_type),
        sa.Column("portfolio", json_type),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )

    op.create_table(
        "document_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("source_url", sa.Text(), nullable=False, unique=True),
        sa.Column("source_domain", sa.String(255), nullable=False),
        sa.Column("trust_tier", sa.String(32), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_sources_source_domain",
        "document_sources",
        ["source_domain"],
    )

    op.create_table(
        "document_versions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "source_id",
            sa.String(36),
            sa.ForeignKey("document_sources.id"),
            nullable=False,
        ),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("doc_type", sa.String(64), nullable=False),
        sa.Column("subject_code", sa.String(64)),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("version", sa.String(128), nullable=False),
        sa.Column("publish_date", sa.Date()),
        sa.Column("effective_date", sa.Date()),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("is_current", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_versions_source_id",
        "document_versions",
        ["source_id"],
    )
    op.create_index(
        "ix_document_versions_doc_type",
        "document_versions",
        ["doc_type"],
    )
    op.create_index(
        "ix_document_versions_subject_code",
        "document_versions",
        ["subject_code"],
    )
    op.create_index(
        "ix_document_versions_content_sha256",
        "document_versions",
        ["content_sha256"],
    )
    op.create_index(
        "ix_document_versions_status",
        "document_versions",
        ["status"],
    )
    op.create_index(
        "ix_document_versions_is_current",
        "document_versions",
        ["is_current"],
    )
    op.create_index(
        "ix_document_versions_current_subject",
        "document_versions",
        ["is_current", "subject_code", "doc_type"],
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "document_version_id",
            sa.String(36),
            sa.ForeignKey("document_versions.id"),
            nullable=False,
        ),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("page_start", sa.Integer()),
        sa.Column("page_end", sa.Integer()),
        sa.Column("section_path", json_type, nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("embedding_model", sa.String(255), nullable=False),
        sa.Column("embedding", vector_type),
        sa.Column("metadata_json", json_type, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_document_chunks_document_version_id",
        "document_chunks",
        ["document_version_id"],
    )
    op.create_index(
        "ix_document_chunks_content_sha256",
        "document_chunks",
        ["content_sha256"],
    )
    op.create_index(
        "ux_document_chunk_version_index",
        "document_chunks",
        ["document_version_id", "chunk_index"],
        unique=True,
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("document_versions")
    op.drop_table("document_sources")
    op.drop_table("user_state")
    op.drop_table("reports")
    op.drop_table("claim_records")
    op.drop_table("evidence_records")
    op.drop_table("tasks")
    op.drop_table("conversations")
