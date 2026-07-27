"""模型层冒烟自检：加载配置 + 真实调用一次 DeepSeek。

用法：
    python scripts/check_llm.py

不带参数时：打印配置解析结果，并向配置的默认模型发一条最小请求，
验证 LiteLLM + 外部 API 是否打通。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 让脚本无需安装包即可导入 src 下的模块
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from financial_agent.config import get_config  # noqa: E402
from financial_agent.models import get_llm_client, system, user  # noqa: E402


def main() -> int:
    config = get_config()
    default_alias = config.models.default
    entry = config.models.resolve()
    provider = config.models.providers[entry.provider]

    masked_key = provider.api_key[:6] + "..." + provider.api_key[-4:]
    print("=== 配置解析 ===")
    print(f"默认模型别名 : {default_alias}")
    print(f"LiteLLM 模型 : {entry.litellm_model}")
    print(f"供应商       : {entry.provider}")
    print(f"api_base     : {provider.api_base}")
    print(f"api_key      : {masked_key}")
    print(f"temperature  : {entry.temperature}")
    print(f"max_tokens   : {entry.max_tokens}")

    print("\n=== 真实调用测试 ===")
    client = get_llm_client()
    reply = client.complete(
        [
            system("你是一个测试助手，请用一句话回答。"),
            user("请回复：模型接入成功。"),
        ],
        max_tokens=64,
    )
    print(f"模型回复     : {reply.strip()}")
    print("\nLiteLLM + 外部模型 API 接入正常 ✓")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
