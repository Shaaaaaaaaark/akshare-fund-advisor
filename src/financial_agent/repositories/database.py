"""SQLAlchemy transaction repository for tasks, evidence and reports."""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import UUID

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    create_engine,
    delete,
    desc,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column

from financial_agent.config import AppConfig, get_config

JSON_TYPE = JSON().with_variant(JSONB(), "postgresql")
VECTOR_TYPE = Vector(1024).with_variant(JSON(), "sqlite")


def _conversation_title(query: str, maximum: int = 24) -> str:
    normalized = " ".join(query.split())
    return normalized if len(normalized) <= maximum else f"{normalized[:maximum]}..."


class Base(DeclarativeBase):
    pass


class ConversationRow(Base):
    __tablename__ = "conversations"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class TaskRow(Base):
    __tablename__ = "tasks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    conversation_id: Mapped[str] = mapped_column(
        ForeignKey("conversations.id"),
        index=True,
    )
    trace_id: Mapped[str] = mapped_column(String(64), index=True)
    query: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(32), index=True)
    state: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class EvidenceRow(Base):
    __tablename__ = "evidence_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    evidence_type: Mapped[str] = mapped_column(String(32), index=True)
    subject_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_id: Mapped[str] = mapped_column(String(128), index=True)
    field: Mapped[str] = mapped_column(String(255), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)


class ClaimRow(Base):
    __tablename__ = "claim_records"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(ForeignKey("tasks.id"), index=True)
    claim_type: Mapped[str] = mapped_column(String(32), index=True)
    allowed: Mapped[bool]
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)


class ReportRow(Base):
    __tablename__ = "reports"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_id: Mapped[str] = mapped_column(
        ForeignKey("tasks.id"),
        unique=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(32), index=True)
    evidence_grade: Mapped[str] = mapped_column(String(1), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class UserStateRow(Base):
    __tablename__ = "user_state"

    user_id: Mapped[str] = mapped_column(String(64), primary_key=True)
    risk_profile: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    portfolio: Mapped[dict[str, Any] | None] = mapped_column(JSON_TYPE)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentSourceRow(Base):
    __tablename__ = "document_sources"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_url: Mapped[str] = mapped_column(Text, unique=True)
    source_domain: Mapped[str] = mapped_column(String(255), index=True)
    trust_tier: Mapped[str] = mapped_column(String(32), index=True)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentVersionRow(Base):
    __tablename__ = "document_versions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    source_id: Mapped[str] = mapped_column(
        ForeignKey("document_sources.id"),
        index=True,
    )
    title: Mapped[str] = mapped_column(Text)
    doc_type: Mapped[str] = mapped_column(String(64), index=True)
    subject_code: Mapped[str | None] = mapped_column(String(64), index=True)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    version: Mapped[str] = mapped_column(String(128))
    publish_date: Mapped[Any | None] = mapped_column(Date)
    effective_date: Mapped[Any | None] = mapped_column(Date)
    status: Mapped[str] = mapped_column(String(32), index=True)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class DocumentChunkRow(Base):
    __tablename__ = "document_chunks"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    document_version_id: Mapped[str] = mapped_column(
        ForeignKey("document_versions.id"),
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer)
    page_start: Mapped[int | None] = mapped_column(Integer)
    page_end: Mapped[int | None] = mapped_column(Integer)
    section_path: Mapped[list[str]] = mapped_column(JSON_TYPE)
    content: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64), index=True)
    embedding_model: Mapped[str] = mapped_column(String(255))
    embedding: Mapped[list[float] | None] = mapped_column(VECTOR_TYPE)
    metadata_json: Mapped[dict[str, Any]] = mapped_column(JSON_TYPE)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


Index("ix_evidence_subject_field", EvidenceRow.subject_id, EvidenceRow.field)
Index(
    "ix_document_versions_current_subject",
    DocumentVersionRow.is_current,
    DocumentVersionRow.subject_code,
    DocumentVersionRow.doc_type,
)
Index(
    "ux_document_chunk_version_index",
    DocumentChunkRow.document_version_id,
    DocumentChunkRow.chunk_index,
    unique=True,
)


class SQLRepository:
    def __init__(self, config: AppConfig | None = None) -> None:
        self._config = config or get_config()
        url = self._config.storage.database_url
        if url.startswith("sqlite:///"):
            database_path = Path(url.removeprefix("sqlite:///"))
            database_path.parent.mkdir(parents=True, exist_ok=True)
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        self.engine = create_engine(
            url,
            pool_pre_ping=True,
            connect_args=connect_args,
        )

    def initialize(self) -> None:
        if self._config.storage.create_schema:
            if self.engine.dialect.name == "postgresql":
                with self.engine.begin() as connection:
                    connection.exec_driver_sql("CREATE EXTENSION IF NOT EXISTS vector")
            Base.metadata.create_all(self.engine)

    def healthcheck(self) -> bool:
        try:
            with self.engine.connect() as connection:
                connection.exec_driver_sql("SELECT 1")
            return True
        except Exception:
            return False

    def create_conversation(self, conversation_id: UUID, now: datetime) -> None:
        with Session(self.engine) as session, session.begin():
            if session.get(ConversationRow, str(conversation_id)) is None:
                session.add(ConversationRow(id=str(conversation_id), created_at=now))

    def conversation_exists(self, conversation_id: UUID) -> bool:
        with Session(self.engine) as session:
            return session.get(ConversationRow, str(conversation_id)) is not None

    def list_conversations(self, limit: int = 50) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            conversations = session.scalars(
                select(ConversationRow)
                .order_by(desc(ConversationRow.created_at))
                .limit(limit)
            ).all()
            result: list[dict[str, Any]] = []
            for conversation in conversations:
                tasks = session.scalars(
                    select(TaskRow)
                    .where(TaskRow.conversation_id == conversation.id)
                    .order_by(TaskRow.created_at)
                ).all()
                first = tasks[0] if tasks else None
                latest = tasks[-1] if tasks else None
                latest_report = (
                    (latest.state or {}).get("final_report")
                    if latest is not None
                    else None
                )
                result.append(
                    {
                        "conversation_id": conversation.id,
                        "title": (
                            _conversation_title(first.query)
                            if first is not None
                            else "新对话"
                        ),
                        "preview": (
                            str(latest_report.get("summary", ""))
                            if latest_report
                            else latest.query
                            if latest is not None
                            else "尚未开始研究"
                        ),
                        "created_at": conversation.created_at,
                        "updated_at": (
                            latest.updated_at
                            if latest is not None
                            else conversation.created_at
                        ),
                        "message_count": sum(
                            1 + int(bool((item.state or {}).get("status")))
                            for item in tasks
                        ),
                    }
                )
            result.sort(key=lambda item: item["updated_at"], reverse=True)
            return result

    def get_conversation(self, conversation_id: UUID) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            conversation = session.get(ConversationRow, str(conversation_id))
            if conversation is None:
                return None
            tasks = session.scalars(
                select(TaskRow)
                .where(TaskRow.conversation_id == conversation.id)
                .order_by(TaskRow.created_at)
            ).all()
            messages: list[dict[str, Any]] = []
            for task in tasks:
                messages.append(
                    {
                        "message_id": f"{task.id}:user",
                        "role": "user",
                        "content": task.query,
                        "created_at": task.created_at,
                        "task_id": task.id,
                        "status": task.status,
                    }
                )
                state = task.state or {}
                report = state.get("final_report")
                clarification = state.get("clarification")
                errors = state.get("errors", [])
                if report:
                    content = str(report.get("summary") or "研究报告已生成。")
                    report_id = report.get("report_id")
                elif clarification:
                    content = str(
                        clarification.get("question")
                        or "请补充更明确的研究对象。"
                    )
                    report_id = None
                elif errors:
                    content = str(errors[0].get("message") or "本次研究未完成。")
                    report_id = None
                elif task.status == "running":
                    continue
                else:
                    content = "本次研究未生成报告。"
                    report_id = None
                messages.append(
                    {
                        "message_id": f"{task.id}:assistant",
                        "role": "assistant",
                        "content": content,
                        "created_at": task.updated_at,
                        "task_id": task.id,
                        "report_id": report_id,
                        "status": task.status,
                        "clarification": clarification,
                        "report": report,
                    }
                )
            return {
                "conversation_id": conversation.id,
                "title": (
                    _conversation_title(tasks[0].query)
                    if tasks
                    else "新对话"
                ),
                "created_at": conversation.created_at,
                "messages": messages,
            }

    def get_conversation_context(
        self,
        conversation_id: UUID,
        limit: int = 8,
    ) -> list[dict[str, Any]]:
        with Session(self.engine) as session:
            tasks = session.scalars(
                select(TaskRow)
                .where(
                    TaskRow.conversation_id == str(conversation_id),
                    TaskRow.status != "running",
                )
                .order_by(desc(TaskRow.created_at))
                .limit(limit)
            ).all()
            result: list[dict[str, Any]] = []
            for task in reversed(tasks):
                state = task.state or {}
                report = state.get("final_report") or {}
                result.append(
                    {
                        "user_query": task.query,
                        "intent": state.get("intent"),
                        "entities": state.get("entities", []),
                        "assistant_summary": report.get("summary"),
                        "status": task.status,
                    }
                )
            return result

    def save_task_started(
        self,
        *,
        task_id: UUID,
        conversation_id: UUID,
        trace_id: str,
        query: str,
        now: datetime,
    ) -> None:
        self.create_conversation(conversation_id, now)
        with Session(self.engine) as session, session.begin():
            session.merge(
                TaskRow(
                    id=str(task_id),
                    conversation_id=str(conversation_id),
                    trace_id=trace_id,
                    query=query,
                    status="running",
                    state={},
                    created_at=now,
                    updated_at=now,
                )
            )

    def save_task_result(self, state: dict[str, Any], now: datetime) -> str | None:
        task_id = str(state["task_id"])
        report = state.get("final_report") or None
        with Session(self.engine) as session, session.begin():
            task = session.get(TaskRow, task_id)
            if task is None:
                raise KeyError(f"任务不存在：{task_id}")
            task.status = str(state.get("status", "failed"))
            task.state = state
            task.updated_at = now

            session.execute(delete(EvidenceRow).where(EvidenceRow.task_id == task_id))
            session.execute(delete(ClaimRow).where(ClaimRow.task_id == task_id))
            for item in state.get("evidence", []):
                session.add(
                    EvidenceRow(
                        id=str(item["evidence_id"]),
                        task_id=task_id,
                        evidence_type=str(item["type"]),
                        subject_type=str(item["subject"]["type"]),
                        subject_id=str(item["subject"]["id"]),
                        field=str(item["field"]),
                        payload=item,
                    )
                )
            for item in state.get("claims", []):
                session.add(
                    ClaimRow(
                        id=str(item["claim_id"]),
                        task_id=task_id,
                        claim_type=str(item["claim_type"]),
                        allowed=bool(item["allowed"]),
                        payload=item,
                    )
                )

            if not report:
                return None
            report_id = str(report["report_id"])
            existing = session.scalar(select(ReportRow).where(ReportRow.task_id == task_id))
            if existing is None:
                session.add(
                    ReportRow(
                        id=report_id,
                        task_id=task_id,
                        status=str(report["status"]),
                        evidence_grade=str(report["evidence_grade"]),
                        payload=report,
                        created_at=now,
                    )
                )
            else:
                existing.status = str(report["status"])
                existing.evidence_grade = str(report["evidence_grade"])
                existing.payload = report
                report_id = existing.id
            return report_id

    def get_task(self, task_id: UUID) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(TaskRow, str(task_id))
            if row is None:
                return None
            return {
                "task_id": row.id,
                "conversation_id": row.conversation_id,
                "trace_id": row.trace_id,
                "query": row.query,
                "status": row.status,
                "state": row.state,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
            }

    def get_report(self, report_id: UUID) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            row = session.get(ReportRow, str(report_id))
            return row.payload if row is not None else None

    def get_report_task_state(self, report_id: UUID) -> dict[str, Any] | None:
        with Session(self.engine) as session:
            report = session.get(ReportRow, str(report_id))
            if report is None:
                return None
            task = session.get(TaskRow, report.task_id)
            return task.state if task is not None else None

    def get_report_evidence(self, report_id: UUID) -> list[dict[str, Any]] | None:
        with Session(self.engine) as session:
            report = session.get(ReportRow, str(report_id))
            if report is None:
                return None
            rows = session.scalars(
                select(EvidenceRow).where(EvidenceRow.task_id == report.task_id)
            ).all()
            return [item.payload for item in rows]

    def put_risk_profile(self, payload: dict[str, Any], now: datetime) -> None:
        self._upsert_user_state("risk_profile", payload, now)

    def put_portfolio(self, payload: dict[str, Any], now: datetime) -> None:
        self._upsert_user_state("portfolio", payload, now)

    def get_user_state(self) -> dict[str, Any]:
        with Session(self.engine) as session:
            row = session.get(UserStateRow, "me")
            if row is None:
                return {"risk_profile": None, "portfolio": None}
            return {
                "risk_profile": row.risk_profile,
                "portfolio": row.portfolio,
            }

    def publish_document(
        self,
        *,
        source: dict[str, Any],
        version: dict[str, Any],
        chunks: list[dict[str, Any]],
        now: datetime,
    ) -> None:
        """Atomically publish a complete document version and its chunks."""
        with Session(self.engine) as session, session.begin():
            source_row = session.get(DocumentSourceRow, str(source["id"]))
            if source_row is None:
                source_row = DocumentSourceRow(
                    id=str(source["id"]),
                    source_url=str(source["source_url"]),
                    source_domain=str(source["source_domain"]),
                    trust_tier=str(source.get("trust_tier", "official")),
                    enabled=True,
                    created_at=now,
                )
                session.add(source_row)

            current_versions = session.scalars(
                select(DocumentVersionRow).where(
                    DocumentVersionRow.source_id == source_row.id,
                    DocumentVersionRow.is_current.is_(True),
                )
            ).all()
            for current in current_versions:
                current.is_current = False

            version_row = DocumentVersionRow(
                id=str(version["id"]),
                source_id=source_row.id,
                title=str(version["title"]),
                doc_type=str(version["doc_type"]),
                subject_code=version.get("subject_code"),
                content_sha256=str(version["content_sha256"]),
                version=str(version["version"]),
                publish_date=version.get("publish_date"),
                effective_date=version.get("effective_date"),
                status="PUBLISHED",
                is_current=True,
                metadata_json=dict(version.get("metadata", {})),
                created_at=now,
            )
            session.add(version_row)
            for item in chunks:
                session.add(
                    DocumentChunkRow(
                        id=str(item["id"]),
                        document_version_id=version_row.id,
                        chunk_index=int(item["chunk_index"]),
                        page_start=item.get("page_start"),
                        page_end=item.get("page_end"),
                        section_path=list(item.get("section_path", [])),
                        content=str(item["content"]),
                        content_sha256=str(item["content_sha256"]),
                        embedding_model=str(item["embedding_model"]),
                        embedding=item.get("embedding"),
                        metadata_json=dict(item.get("metadata", {})),
                        created_at=now,
                    )
                )

    def semantic_search(
        self,
        *,
        query_embedding: list[float],
        subject_code: str | None,
        doc_types: list[str],
        limit: int,
    ) -> list[dict[str, Any]]:
        if self.engine.dialect.name != "postgresql":
            return []
        distance = DocumentChunkRow.embedding.cosine_distance(query_embedding)
        statement = (
            select(
                DocumentChunkRow,
                DocumentVersionRow,
                DocumentSourceRow,
                distance.label("distance"),
            )
            .join(
                DocumentVersionRow,
                DocumentVersionRow.id == DocumentChunkRow.document_version_id,
            )
            .join(
                DocumentSourceRow,
                DocumentSourceRow.id == DocumentVersionRow.source_id,
            )
            .where(
                DocumentVersionRow.is_current.is_(True),
                DocumentVersionRow.status == "PUBLISHED",
                DocumentSourceRow.enabled.is_(True),
                DocumentChunkRow.embedding.is_not(None),
            )
        )
        if subject_code:
            statement = statement.where(DocumentVersionRow.subject_code == subject_code)
        if doc_types:
            statement = statement.where(DocumentVersionRow.doc_type.in_(doc_types))
        statement = statement.order_by(distance).limit(limit)

        with Session(self.engine) as session:
            rows = session.execute(statement).all()
            return [
                {
                    "chunk_id": chunk.id,
                    "title": version.title,
                    "url": source.source_url,
                    "text": chunk.content,
                    "score": max(0.0, 1.0 - float(distance_value)),
                    "page": chunk.page_start,
                    "version": version.version,
                    "subject_code": version.subject_code,
                    "doc_type": version.doc_type,
                    "metadata": {
                        **chunk.metadata_json,
                        "section_path": chunk.section_path,
                        "document_version_id": version.id,
                    },
                }
                for chunk, version, source, distance_value in rows
            ]

    def list_current_chunks(self) -> list[dict[str, Any]]:
        """Return authoritative chunks for rebuilding Elasticsearch."""
        statement = (
            select(DocumentChunkRow, DocumentVersionRow, DocumentSourceRow)
            .join(
                DocumentVersionRow,
                DocumentVersionRow.id == DocumentChunkRow.document_version_id,
            )
            .join(
                DocumentSourceRow,
                DocumentSourceRow.id == DocumentVersionRow.source_id,
            )
            .where(
                DocumentVersionRow.is_current.is_(True),
                DocumentVersionRow.status == "PUBLISHED",
                DocumentSourceRow.enabled.is_(True),
            )
        )
        with Session(self.engine) as session:
            rows = session.execute(statement).all()
            return [
                {
                    "chunk_id": chunk.id,
                    "title": version.title,
                    "content": chunk.content,
                    "source_url": source.source_url,
                    "subject_code": version.subject_code,
                    "doc_type": version.doc_type,
                    "document_version_id": version.id,
                    "version": version.version,
                    "page_start": chunk.page_start,
                    "page_end": chunk.page_end,
                    "section_path": chunk.section_path,
                }
                for chunk, version, source in rows
            ]

    def _upsert_user_state(
        self,
        field: str,
        payload: dict[str, Any],
        now: datetime,
    ) -> None:
        with Session(self.engine) as session, session.begin():
            row = session.get(UserStateRow, "me")
            if row is None:
                row = UserStateRow(
                    user_id="me",
                    risk_profile=None,
                    portfolio=None,
                    updated_at=now,
                )
                session.add(row)
            setattr(row, field, payload)
            row.updated_at = now
