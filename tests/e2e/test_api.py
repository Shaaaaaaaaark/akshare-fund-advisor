from __future__ import annotations

from datetime import datetime, timedelta, timezone

from conftest import FakeFundToolClient
from fastapi.testclient import TestClient

from financial_agent.api.app import create_app
from financial_agent.orchestration import FinancialAgentGraph
from financial_agent.repositories import SQLRepository


def test_frontend_and_assets_are_served(test_config) -> None:
    client = TestClient(
        create_app(
            test_config,
            graph=FinancialAgentGraph(
                test_config,
                tool_client=FakeFundToolClient(),
            ),
            repository=SQLRepository(test_config),
        )
    )

    index = client.get("/")
    stylesheet = client.get("/assets/styles.css")
    script = client.get("/assets/app.js")

    assert index.status_code == 200
    assert "基金研究 Agent" in index.text
    assert stylesheet.status_code == 200
    assert "--green:" in stylesheet.text
    assert script.status_code == 200
    assert 'api("/health/ready")' in script.text


def test_message_to_report_and_evidence(test_config) -> None:
    repository = SQLRepository(test_config)
    graph = FinancialAgentGraph(
        test_config,
        tool_client=FakeFundToolClient(),
    )
    client = TestClient(create_app(test_config, graph=graph, repository=repository))
    assert client.get("/health/ready").json() == {
        "status": "ok",
        "checks": {"database": True, "mcp": True},
    }

    conversation = client.post("/v1/conversations").json()
    response = client.post(
        f"/v1/conversations/{conversation['conversation_id']}/messages",
        json={"content": "沪深300现在贵吗"},
    )

    assert response.status_code == 200
    accepted = response.json()
    assert accepted["status"] == "completed"
    assert accepted["report_id"]

    report = client.get(f"/v1/reports/{accepted['report_id']}")
    evidence = client.get(f"/v1/reports/{accepted['report_id']}/evidence")
    task = client.get(f"/v1/tasks/{accepted['task_id']}")

    assert report.status_code == 200
    assert report.json()["evidence_grade"] == "A"
    assert evidence.status_code == 200
    assert evidence.json()["evidence"]
    assert task.json()["report_id"] == accepted["report_id"]


def test_conversation_memory_is_scoped_and_chart_is_audited(test_config) -> None:
    tool_client = FakeFundToolClient()
    client = TestClient(
        create_app(
            test_config,
            graph=FinancialAgentGraph(test_config, tool_client=tool_client),
            repository=SQLRepository(test_config),
        )
    )
    first = client.post("/v1/conversations").json()["conversation_id"]

    initial = client.post(
        f"/v1/conversations/{first}/messages",
        json={"content": "沪深300现在贵吗"},
    ).json()
    follow_up = client.post(
        f"/v1/conversations/{first}/messages",
        json={"content": "那 PB 呢？"},
    ).json()

    assert initial["status"] == "completed"
    assert follow_up["status"] == "completed"
    assert tool_client.calls[-1] == (
        "index_valuation",
        {"index": "沪深300", "years": 10, "max_points": 600},
    )

    detail = client.get(f"/v1/conversations/{first}").json()
    conversations = client.get("/v1/conversations").json()
    chart = client.get(
        f"/v1/reports/{follow_up['report_id']}/valuation-chart"
    ).json()

    assert len(detail["messages"]) == 4
    assert conversations[0]["conversation_id"] == first
    assert chart["available"] is True
    assert set(chart["metrics"]) == {"pe_ttm", "pb", "market_price"}
    assert chart["metrics"]["pe_ttm"]["reference_lines"]["opportunity"] == 10.5

    second = client.post("/v1/conversations").json()["conversation_id"]
    isolated = client.post(
        f"/v1/conversations/{second}/messages",
        json={"content": "那 PB 呢？"},
    ).json()

    assert isolated["status"] == "need_clarification"
    assert len(tool_client.calls) == 2


def test_user_profile_and_portfolio_are_validated(test_config) -> None:
    client = TestClient(
        create_app(
            test_config,
            graph=FinancialAgentGraph(
                test_config,
                tool_client=FakeFundToolClient(),
            ),
            repository=SQLRepository(test_config),
        )
    )
    now = datetime.now(timezone.utc)
    profile = {
        "risk_level": "balanced",
        "horizon_months": 60,
        "max_drawdown_tolerance_pct": "20",
        "emergency_fund_ready": True,
        "stable_cash_flow": True,
        "target_allocation": {"equity": "60", "cash": "40"},
        "assessed_at": now.isoformat(),
        "expires_at": (now + timedelta(days=365)).isoformat(),
    }
    portfolio = {
        "positions": [
            {
                "fund_code": "510300",
                "share_class": None,
                "channel": "exchange",
                "units": "100",
                "average_cost": "4.1",
                "currency": "CNY",
                "target_weight_pct": "30",
                "updated_at": now.isoformat(),
            }
        ]
    }

    assert client.put("/v1/users/me/risk-profile", json=profile).status_code == 200
    assert client.put("/v1/users/me/portfolio", json=portfolio).status_code == 200


def test_invalid_fund_code_is_rejected(test_config) -> None:
    client = TestClient(
        create_app(
            test_config,
            graph=FinancialAgentGraph(
                test_config,
                tool_client=FakeFundToolClient(),
            ),
            repository=SQLRepository(test_config),
        )
    )
    response = client.put(
        "/v1/users/me/portfolio",
        json={
            "positions": [
                {
                    "fund_code": "BAD",
                    "channel": "exchange",
                    "units": "1",
                    "average_cost": "1",
                    "currency": "CNY",
                    "updated_at": datetime.now(timezone.utc).isoformat(),
                }
            ]
        },
    )
    assert response.status_code == 422
