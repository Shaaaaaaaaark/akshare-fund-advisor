from datetime import datetime
from zoneinfo import ZoneInfo

from fund_advisor_mcp.fund.adapter import FundAdvisorToolAdapter

SHANGHAI = ZoneInfo("Asia/Shanghai")


class FakeAdvisor:
    def search(self, query, limit):
        return {
            "ok": True,
            "action": "search",
            "query": query,
            "count": 1,
            "results": [{"code": "000001", "name": "示例基金"}],
        }

    def common_output(self):
        return {
            "queried_at": datetime.now(SHANGHAI),
            "sources": [{"provider": "AKShare", "interface": "fund_name_em"}],
            "data_audit": [
                {
                    "interface": "fund_name_em",
                    "validation": "passed",
                    "frame_sha256": "source-hash",
                }
            ],
            "data_warnings": [],
            "data_policy": {"ai_may_generate_market_data": False},
        }


def test_adapter_preserves_skill_data_and_audit(test_config) -> None:
    adapter = FundAdvisorToolAdapter(
        test_config,
        advisor_factory=FakeAdvisor,
    )

    envelope = adapter.fund_search(query="示例", limit=5)

    assert envelope.ok
    assert envelope.data["results"][0]["code"] == "000001"
    assert envelope.data_audit[0]["frame_sha256"] == "source-hash"
    assert envelope.data_policy["ai_may_generate_market_data"] is False


def test_adapter_reuses_complete_cached_envelope(test_config) -> None:
    calls = 0

    def factory():
        nonlocal calls
        calls += 1
        return FakeAdvisor()

    adapter = FundAdvisorToolAdapter(test_config, advisor_factory=factory)
    first = adapter.fund_search(query="示例", limit=5)
    second = adapter.fund_search(query="示例", limit=5)

    assert calls == 1
    assert first.request_id == second.request_id
    assert second.data_audit == first.data_audit
