"""Load the independently packaged Skill without duplicating its implementation."""

from __future__ import annotations

import importlib.util
import os
import sys
from functools import lru_cache
from pathlib import Path
from types import ModuleType


def _find_skill_script() -> Path:
    configured = os.environ.get("FINAGENT_SKILL_DIR")
    roots = [
        Path(configured).expanduser() if configured else None,
        Path.cwd() / "skills" / "akshare-fund-advisor",
        Path(__file__).resolve().parents[3] / "skills" / "akshare-fund-advisor",
    ]
    candidates = [
        root / "scripts" / "fund_advisor.py"
        for root in roots
        if root is not None
    ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    searched = "、".join(str(item) for item in candidates)
    raise FileNotFoundError(f"Fund Advisor Skill 不存在，已检查：{searched}")


@lru_cache(maxsize=1)
def load_skill_module() -> ModuleType:
    script = _find_skill_script()

    module_name = "akshare_fund_advisor_runtime"
    spec = importlib.util.spec_from_file_location(module_name, script)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载 Fund Advisor Skill：{script}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module
