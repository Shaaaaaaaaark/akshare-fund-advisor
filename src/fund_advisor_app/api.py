"""FastAPI application exposing the shared Agent chat service."""

from __future__ import annotations

import argparse
import json
from collections.abc import AsyncIterator, Sequence

from fastapi import FastAPI, HTTPException, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, StreamingResponse

from fund_advisor_mcp.config import AppConfig, get_config

from .schemas import ChatRequest, SessionView, StreamEvent
from .service import AgentChatService
from .sessions import SessionCapacityError


def create_app(
    *,
    config: AppConfig | None = None,
    service: AgentChatService | None = None,
) -> FastAPI:
    settings = config or get_config()
    chat_service = service or AgentChatService(config=settings)
    application = FastAPI(
        title="Fund Advisor Agent API",
        version="0.1.0",
        docs_url="/api/docs",
        redoc_url=None,
    )
    application.state.chat_service = chat_service
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.app.allowed_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "DELETE"],
        allow_headers=["Content-Type"],
    )

    @application.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    @application.post("/api/sessions", response_model=SessionView)
    async def create_session() -> SessionView:
        try:
            return await chat_service.create_session()
        except SessionCapacityError as exc:
            raise HTTPException(
                status_code=503,
                detail="临时会话已满，请稍后重试",
            ) from exc

    @application.get(
        "/api/sessions/{session_id}",
        response_model=SessionView,
    )
    async def get_session(session_id: str) -> SessionView:
        session = await chat_service.get_session(session_id)
        if session is None:
            raise HTTPException(status_code=404, detail="会话不存在或已过期")
        return session

    @application.delete(
        "/api/sessions/{session_id}",
        status_code=204,
    )
    async def delete_session(session_id: str) -> Response:
        await chat_service.delete_session(session_id)
        return Response(status_code=204)

    @application.post("/api/chat/stream")
    async def chat_stream(request: ChatRequest) -> StreamingResponse:
        async def events() -> AsyncIterator[str]:
            try:
                async for item in chat_service.stream(
                    message=request.message,
                    session_id=request.session_id,
                ):
                    yield _encode_sse(item)
            except SessionCapacityError:
                yield _encode_sse(
                    StreamEvent(
                        event="error",
                        data={
                            "code": "SESSION_CAPACITY_EXCEEDED",
                            "message": "临时会话已满，请稍后重试",
                        },
                    )
                )
                yield _encode_sse(StreamEvent(event="done", data={}))
            except Exception as exc:
                yield _encode_sse(
                    StreamEvent(
                        event="error",
                        data={
                            "code": "AGENT_API_ERROR",
                            "message": "研究请求处理失败",
                            "reason": type(exc).__name__,
                        },
                    )
                )
                yield _encode_sse(StreamEvent(event="done", data={}))

        return StreamingResponse(
            events(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "X-Accel-Buffering": "no",
            },
        )

    @application.get("/")
    async def api_root() -> JSONResponse:
        return JSONResponse(
            {
                "name": "Fund Advisor Agent API",
                "docs": "/api/docs",
            }
        )

    return application


def _encode_sse(item: StreamEvent) -> str:
    payload = json.dumps(
        item.data,
        ensure_ascii=False,
        separators=(",", ":"),
    )
    return f"event: {item.event}\ndata: {payload}\n\n"


app = create_app()


def build_parser() -> argparse.ArgumentParser:
    settings = get_config()
    parser = argparse.ArgumentParser(
        prog="fund-advisor-api",
        description="Serve the Fund Advisor Agent API",
    )
    parser.add_argument("--host", default=settings.app.host)
    parser.add_argument("--port", type=int, default=settings.app.port)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    import uvicorn

    args = build_parser().parse_args(argv)
    uvicorn.run(
        app,
        host=args.host,
        port=args.port,
        log_level="info",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
