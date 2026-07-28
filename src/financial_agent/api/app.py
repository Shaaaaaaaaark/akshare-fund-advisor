"""FastAPI application for the financial research agent."""

from __future__ import annotations

import asyncio
import logging
import secrets
from datetime import datetime
from typing import Annotated, Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from fastapi import Depends, FastAPI, Header, HTTPException, status
from fastapi.responses import FileResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles

from financial_agent.config import AppConfig, get_config
from financial_agent.observability import (
    ElasticsearchAuditProjection,
    configure_logging,
    configure_tracing,
)
from financial_agent.orchestration import FinancialAgentGraph
from financial_agent.portfolio import Portfolio, RiskProfile
from financial_agent.rag import build_rag_service
from financial_agent.repositories import SQLRepository
from financial_agent.web import WEB_ROOT
from financial_agent.web_research import build_web_research_client

from .schemas import (
    ConversationCreated,
    ConversationDetail,
    ConversationSummary,
    HealthResponse,
    MessageAccepted,
    MessageRequest,
    TaskResponse,
)
from .valuation import valuation_chart_from_state

SHANGHAI = ZoneInfo("Asia/Shanghai")
bearer = HTTPBearer(auto_error=False)
logger = logging.getLogger("financial_agent.api")


def create_app(
    config: AppConfig | None = None,
    *,
    graph: FinancialAgentGraph | None = None,
    repository: SQLRepository | None = None,
) -> FastAPI:
    settings = config or get_config()
    configure_logging(settings.observability.log_level)
    repo = repository or SQLRepository(settings)
    repo.initialize()
    audit_projection = ElasticsearchAuditProjection(settings)
    web_research_client = (
        build_web_research_client(settings)
        if settings.web_research.enabled
        else None
    )
    agent = graph or FinancialAgentGraph(
        settings,
        rag=build_rag_service(settings, repo),
        user_context_loader=repo.get_user_state,
    )

    application = FastAPI(
        title="Financial Investment Research Agent",
        version="0.1.0",
        description=(
            "Evidence-gated research API. Market numbers only come from audited Fund Advisor tools."
        ),
    )
    application.state.config = settings
    application.state.repository = repo
    application.state.graph = agent
    configure_tracing(application)
    application.mount(
        "/assets",
        StaticFiles(directory=WEB_ROOT),
        name="web-assets",
    )

    async def authorize(
        credentials: Annotated[
            HTTPAuthorizationCredentials | None,
            Depends(bearer),
        ],
    ) -> None:
        expected = settings.server.api_token
        if not expected:
            return
        if (
            credentials is None
            or credentials.scheme.lower() != "bearer"
            or not secrets.compare_digest(credentials.credentials, expected)
        ):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="无效的 API Token",
            )

    auth = [Depends(authorize)]

    @application.get("/", include_in_schema=False)
    async def frontend() -> FileResponse:
        return FileResponse(WEB_ROOT / "index.html")

    @application.get("/health/live", response_model=HealthResponse)
    async def liveness() -> HealthResponse:
        return HealthResponse(status="ok", checks={"process": True})

    @application.get("/health/ready", response_model=HealthResponse)
    async def readiness() -> HealthResponse:
        database = await asyncio.to_thread(repo.healthcheck)
        try:
            mcp_ready = await asyncio.wait_for(
                agent.tool_client.healthcheck(),
                timeout=5,
            )
        except (TimeoutError, AttributeError):
            mcp_ready = False
        web_mcp_ready = True
        if web_research_client is not None:
            try:
                web_mcp_ready = await asyncio.wait_for(
                    web_research_client.healthcheck(),
                    timeout=5,
                )
            except (TimeoutError, AttributeError):
                web_mcp_ready = False
        checks = {"database": database, "mcp": mcp_ready}
        if web_research_client is not None:
            checks["web_mcp"] = web_mcp_ready
        return HealthResponse(
            status=(
                "ok"
                if database and mcp_ready and web_mcp_ready
                else "not_ready"
            ),
            checks=checks,
        )

    @application.post(
        "/v1/conversations",
        response_model=ConversationCreated,
        dependencies=auth,
    )
    async def create_conversation() -> ConversationCreated:
        conversation_id = uuid4()
        await asyncio.to_thread(
            repo.create_conversation,
            conversation_id,
            datetime.now(SHANGHAI),
        )
        return ConversationCreated(conversation_id=conversation_id)

    @application.get(
        "/v1/conversations",
        response_model=list[ConversationSummary],
        dependencies=auth,
    )
    async def list_conversations() -> list[ConversationSummary]:
        payload = await asyncio.to_thread(repo.list_conversations)
        return [ConversationSummary.model_validate(item) for item in payload]

    @application.get(
        "/v1/conversations/{conversation_id}",
        response_model=ConversationDetail,
        dependencies=auth,
    )
    async def get_conversation(conversation_id: UUID) -> ConversationDetail:
        payload = await asyncio.to_thread(repo.get_conversation, conversation_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="对话不存在")
        return ConversationDetail.model_validate(payload)

    @application.post(
        "/v1/conversations/{conversation_id}/messages",
        response_model=MessageAccepted,
        dependencies=auth,
    )
    async def create_message(
        conversation_id: UUID,
        body: MessageRequest,
        x_trace_id: Annotated[str | None, Header()] = None,
    ) -> MessageAccepted:
        exists = await asyncio.to_thread(repo.conversation_exists, conversation_id)
        if not exists:
            raise HTTPException(status_code=404, detail="对话不存在")
        conversation_history = await asyncio.to_thread(
            repo.get_conversation_context,
            conversation_id,
        )
        task_id = uuid4()
        trace_id = x_trace_id or str(uuid4())
        now = datetime.now(SHANGHAI)
        await asyncio.to_thread(
            repo.save_task_started,
            task_id=task_id,
            conversation_id=conversation_id,
            trace_id=trace_id,
            query=body.content,
            now=now,
        )
        initial = agent.initial_state(
            body.content,
            conversation_id=conversation_id,
            task_id=task_id,
            trace_id=trace_id,
            conversation_history=conversation_history,
        )
        try:
            result = await agent.ainvoke(initial)
        except Exception as exc:
            failed = {
                **initial,
                "status": "failed",
                "errors": [
                    {
                        "category": "internal",
                        "code": "GRAPH_EXECUTION_FAILED",
                        "message": "Agent 执行失败",
                        "retryable": False,
                        "source": "langgraph",
                        "details": {"reason": str(exc)},
                    }
                ],
            }
            await asyncio.to_thread(
                repo.save_task_result,
                failed,
                datetime.now(SHANGHAI),
            )
            if audit_projection.enabled:
                try:
                    await asyncio.to_thread(
                        audit_projection.index_task,
                        failed,
                    )
                except Exception as index_exc:
                    logger.warning(
                        "Failed task audit projection failed task_id=%s: %s",
                        task_id,
                        index_exc,
                    )
            raise HTTPException(
                status_code=500,
                detail={"message": "Agent 执行失败", "trace_id": trace_id},
            ) from exc

        report_id_text = await asyncio.to_thread(
            repo.save_task_result,
            result,
            datetime.now(SHANGHAI),
        )
        if audit_projection.enabled:
            try:
                await asyncio.to_thread(audit_projection.index_task, result)
            except Exception as exc:
                logger.warning(
                    "Elasticsearch audit projection failed task_id=%s: %s",
                    task_id,
                    exc,
                )
        return MessageAccepted(
            conversation_id=conversation_id,
            task_id=task_id,
            trace_id=trace_id,
            status=result["status"],
            clarification=result.get("clarification"),
            report_id=UUID(report_id_text) if report_id_text else None,
            errors=result.get("errors", []),
        )

    @application.get(
        "/v1/tasks/{task_id}",
        response_model=TaskResponse,
        dependencies=auth,
    )
    async def get_task(task_id: UUID) -> TaskResponse:
        row = await asyncio.to_thread(repo.get_task, task_id)
        if row is None:
            raise HTTPException(status_code=404, detail="任务不存在")
        state = row.get("state") or {}
        report = state.get("final_report") or {}
        return TaskResponse(
            task_id=UUID(row["task_id"]),
            conversation_id=UUID(row["conversation_id"]),
            trace_id=row["trace_id"],
            query=row["query"],
            status=row["status"],
            clarification=state.get("clarification"),
            report_id=UUID(report["report_id"]) if report.get("report_id") else None,
            errors=state.get("errors", []),
        )

    @application.get("/v1/reports/{report_id}", dependencies=auth)
    async def get_report(report_id: UUID) -> dict[str, Any]:
        payload = await asyncio.to_thread(repo.get_report, report_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        return payload

    @application.get("/v1/reports/{report_id}/evidence", dependencies=auth)
    async def get_report_evidence(report_id: UUID) -> dict[str, Any]:
        payload = await asyncio.to_thread(repo.get_report_evidence, report_id)
        if payload is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        return {"report_id": str(report_id), "evidence": payload}

    @application.get("/v1/reports/{report_id}/valuation-chart", dependencies=auth)
    async def get_valuation_chart(report_id: UUID) -> dict[str, Any]:
        state = await asyncio.to_thread(repo.get_report_task_state, report_id)
        if state is None:
            raise HTTPException(status_code=404, detail="报告不存在")
        return valuation_chart_from_state(state)

    @application.put("/v1/users/me/risk-profile", dependencies=auth)
    async def put_risk_profile(profile: RiskProfile) -> dict[str, str]:
        await asyncio.to_thread(
            repo.put_risk_profile,
            profile.model_dump(mode="json"),
            datetime.now(SHANGHAI),
        )
        return {"status": "saved"}

    @application.put("/v1/users/me/portfolio", dependencies=auth)
    async def put_portfolio(portfolio: Portfolio) -> dict[str, str]:
        await asyncio.to_thread(
            repo.put_portfolio,
            portfolio.model_dump(mode="json"),
            datetime.now(SHANGHAI),
        )
        return {"status": "saved"}

    return application


app = create_app()
