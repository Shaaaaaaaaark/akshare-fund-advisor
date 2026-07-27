from pathlib import Path
from types import SimpleNamespace

import pytest

from financial_agent.mcp_client.client import _parse_result
from financial_agent.mcp_server.skill_loader import _find_skill_script


def test_skill_script_can_be_configured_outside_installed_package(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    skill_dir = (
        Path(__file__).resolve().parents[1]
        / "skills"
        / "akshare-fund-advisor"
    )
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("FINAGENT_SKILL_DIR", str(skill_dir))

    script = _find_skill_script()

    assert script == (skill_dir / "scripts" / "fund_advisor.py").resolve()


def test_mcp_tool_error_is_not_parsed_as_json() -> None:
    result = SimpleNamespace(
        isError=True,
        structuredContent=None,
        content=[
            SimpleNamespace(
                text="Error executing tool fund_search: Skill missing",
            )
        ],
    )

    with pytest.raises(RuntimeError, match="Skill missing"):
        _parse_result("fund_search", result)
