"""Command-line entry point for the FastAPI service."""

from __future__ import annotations

import uvicorn

from financial_agent.config import get_config


def main() -> None:
    config = get_config()
    uvicorn.run(
        "financial_agent.api.app:app",
        host=config.server.host,
        port=config.server.port,
        reload=config.server.reload,
    )


if __name__ == "__main__":
    main()
