from datetime import datetime, timedelta, timezone

from financial_agent.domain import Intent
from financial_agent.policies import check_suitability


def test_missing_profile_only_blocks_specific_amount() -> None:
    decision = check_suitability(
        Intent.DCA_REFERENCE,
        {},
        datetime.now(timezone.utc),
    )
    assert decision.general_research_allowed
    assert not decision.specific_amount_allowed
    assert "风险画像" in decision.missing_information


def test_complete_current_profile_allows_amount_calculation() -> None:
    now = datetime.now(timezone.utc)
    decision = check_suitability(
        Intent.DCA_REFERENCE,
        {
            "risk_profile": {
                "risk_level": "balanced",
                "horizon_months": 60,
                "max_drawdown_tolerance_pct": "20",
                "emergency_fund_ready": True,
                "stable_cash_flow": True,
                "target_allocation": {},
                "assessed_at": now.isoformat(),
                "expires_at": (now + timedelta(days=365)).isoformat(),
            },
            "portfolio": {"positions": []},
        },
        now,
    )
    assert decision.specific_amount_allowed
