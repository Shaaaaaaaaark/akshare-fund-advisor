"""模型层：通过 LiteLLM 统一接入外部 OpenAI 兼容模型 API。

对外只暴露一个 LLMClient 和消息辅助函数。上层（编排、报告生成）只依赖
这里的稳定接口，换模型/换供应商只改配置，不改业务代码。
"""

from .client import LLMClient, LLMError, get_llm_client
from .messages import assistant, system, user
from .narrator import ReportNarrator

__all__ = [
    "LLMClient",
    "LLMError",
    "ReportNarrator",
    "get_llm_client",
    "system",
    "user",
    "assistant",
]
