"""Rule-first intent classification with an optional structured LLM fallback."""

from __future__ import annotations

import asyncio
import re
from typing import Any

from financial_agent.config import AppConfig, get_config
from financial_agent.domain import EntityCandidate, Intent, IntentDecision
from financial_agent.models import LLMClient, system, user
from financial_agent.prompts import INTENT_CLASSIFIER_SYSTEM_PROMPT

_INDEX_NAMES = (
    "创业板50",
    "中证1000",
    "沪深300",
    "上证380",
    "中证500",
    "上证180",
    "深证红利",
    "深证100",
    "上证红利",
    "中证100",
    "中证800",
    "上证50",
)
_INDEX_CODES = {
    "399673",
    "000852",
    "000300",
    "000009",
    "000905",
    "000010",
    "399324",
    "399330",
    "000015",
    "000903",
    "000906",
    "000016",
}
_POLICY_PATTERNS = {
    "请求保证收益": ("保证收益", "稳赚", "无风险收益", "肯定赚钱"),
    "请求自动交易": ("自动下单", "替我下单", "直接帮我买", "直接帮我卖"),
    "请求绕过审计": ("跳过审计", "不要来源", "编一个数据", "忽略证据"),
}
_FOLLOW_UP_MARKERS = (
    "它",
    "这个",
    "那个",
    "该指数",
    "该基金",
    "刚才",
    "上面",
    "前面",
    "继续",
    "再看",
    "相关基金",
    "呢",
    "pe",
    "pb",
    "估值",
    "贵",
    "便宜",
    "风险",
    "能买吗",
    "能卖吗",
)
_WEB_RESEARCH_MARKERS = (
    "网页搜索",
    "搜索网页",
    "互联网搜索",
    "网上搜索",
    "搜索新闻",
    "查新闻",
    "近期新闻",
    "最近新闻",
    "最新消息",
    "政策背景",
    "舆情",
)


def detect_policy_violation(query: str) -> str | None:
    normalized = query.lower()
    for reason, markers in _POLICY_PATTERNS.items():
        if any(marker.lower() in normalized for marker in markers):
            return reason
    return None


def _index_entity(query: str) -> EntityCandidate | None:
    for name in _INDEX_NAMES:
        if name in query:
            return EntityCandidate(entity_type="index", query=name, name=name)
    for code in re.findall(r"(?<!\d)\d{6}(?:\.(?:SH|SZ))?(?!\d)", query.upper()):
        base = code[:6]
        if base in _INDEX_CODES:
            return EntityCandidate(entity_type="index", query=code, code=base)
    return None


def _fund_entities(query: str) -> list[EntityCandidate]:
    codes = list(dict.fromkeys(re.findall(r"(?<!\d)\d{6}(?!\d)", query)))
    return [EntityCandidate(entity_type="fund", query=code, code=code) for code in codes]


def _stock_entity(query: str) -> EntityCandidate | None:
    if not any(
        marker in query.lower()
        for marker in ("股票", "个股", "股价", "stock")
    ):
        return None
    codes = re.findall(r"(?<!\d)\d{6}(?!\d)", query)
    if codes:
        return EntityCandidate(
            entity_type="stock",
            query=codes[0],
            code=codes[0],
        )
    cleaned = re.sub(
        r"(请|帮我|看一下|看看|分析|股票|个股|股价|估值|市盈率|市净率|"
        r"PE|PB|现在|目前|怎么样|贵吗|便宜吗)",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。？?")
    return (
        EntityCandidate(entity_type="stock", query=cleaned, name=cleaned)
        if cleaned
        else None
    )


def _clean_subject(query: str) -> str:
    cleaned = re.sub(
        r"(请|帮我|一下|现在|目前|基金|分析|看看|怎么样|能买吗|能卖吗|"
        r"搜索|查找|找基金|估值|贵吗|便宜吗|定投|参考|申购|赎回|状态|"
        r"对比|比较)",
        " ",
        query,
        flags=re.IGNORECASE,
    )
    cleaned = re.sub(r"\s+", " ", cleaned).strip(" ，,。？?")
    return cleaned or query.strip()


def contextualize_query(
    query: str,
    history: list[dict[str, Any]],
) -> str:
    """Resolve a follow-up only from turns in the same conversation."""
    text = query.strip()
    if (
        not text
        or _index_entity(text) is not None
        or bool(_fund_entities(text))
        or re.search(r"https?://", text)
        or not any(marker.lower() in text.lower() for marker in _FOLLOW_UP_MARKERS)
    ):
        return text

    for turn in reversed(history):
        for raw in reversed(turn.get("entities") or []):
            if raw.get("entity_type") not in {"index", "fund", "stock"}:
                continue
            subject = raw.get("name") or raw.get("code") or raw.get("query")
            if subject:
                return f"{subject} {text}"
    return text


def classify_by_rules(query: str) -> IntentDecision:
    text = query.strip()
    if not text:
        return IntentDecision(
            intent=Intent.UNSUPPORTED,
            needs_clarification=True,
            clarification_question="请输入要研究的基金、ETF 或指数。",
            confidence=1.0,
        )

    index = _index_entity(text)
    funds = _fund_entities(text)
    stock = _stock_entity(text)
    lowered = text.lower()
    has_url = bool(re.search(r"https?://", text))

    if has_url or any(marker in text for marker in ("这份文档", "招募说明书", "基金合同")):
        return IntentDecision(
            intent=Intent.DOCUMENT_QA,
            entities=[
                EntityCandidate(
                    entity_type="document",
                    query=re.search(r"https?://\S+", text).group(0) if has_url else text,
                )
            ],
            confidence=0.98,
        )
    if any(marker in text for marker in _WEB_RESEARCH_MARKERS):
        return IntentDecision(
            intent=Intent.WEB_RESEARCH,
            entities=[
                EntityCandidate(
                    entity_type="web_query",
                    query=text,
                )
            ],
            confidence=0.98,
        )
    if stock is not None:
        return IntentDecision(
            intent=Intent.STOCK_VALUATION,
            entities=[stock],
            confidence=0.97,
        )
    if any(marker in text for marker in ("比较", "对比", "哪个好", "差异")):
        entities = funds or [
            EntityCandidate(entity_type="fund", query=item.strip())
            for item in re.split(r"[、,，和与]", _clean_subject(text))
            if item.strip()
        ]
        return IntentDecision(
            intent=Intent.FUND_COMPARE,
            entities=entities,
            needs_clarification=len(entities) < 2,
            clarification_question=(
                "请提供两到五只基金的明确代码。" if len(entities) < 2 else None
            ),
            confidence=0.95,
        )
    if any(marker in text for marker in ("定投", "分批投入")):
        entity = index or (funds[0] if funds else None)
        return IntentDecision(
            intent=Intent.DCA_REFERENCE,
            entities=[entity]
            if entity
            else [EntityCandidate(entity_type="fund", query=_clean_subject(text))],
            confidence=0.94,
        )
    if any(marker in text for marker in ("卖出", "止盈", "再平衡", "减仓")):
        return IntentDecision(
            intent=Intent.SELL_OR_REBALANCE,
            entities=funds or [EntityCandidate(entity_type="fund", query=_clean_subject(text))],
            confidence=0.94,
        )
    if index and (
        any(marker in text for marker in ("估值", "贵", "便宜", "市盈率", "市净率"))
        or "pe" in lowered
        or "pb" in lowered
    ):
        return IntentDecision(
            intent=Intent.INDEX_VALUATION,
            entities=[index],
            confidence=0.99,
        )
    if any(marker in text for marker in ("评级", "星级", "几星", "评分", "晨星")):
        return IntentDecision(
            intent=Intent.FUND_RATING,
            entities=funds or [EntityCandidate(entity_type="fund", query=_clean_subject(text))],
            needs_clarification=not funds,
            clarification_question=(
                "请提供基金的明确 6 位代码以查询评级。" if not funds else None
            ),
            confidence=0.95,
        )
    if any(
        marker in text
        for marker in (
            "费率",
            "费用",
            "手续费",
            "管理费",
            "托管费",
            "申购费",
            "赎回费",
            "持仓",
            "重仓",
            "资产配置",
            "仓位",
            "档案",
            "基本信息",
            "基金经理",
        )
    ):
        return IntentDecision(
            intent=Intent.FUND_PROFILE,
            entities=funds or [EntityCandidate(entity_type="fund", query=_clean_subject(text))],
            needs_clarification=not funds,
            clarification_question=(
                "请提供基金的明确 6 位代码以查询档案。" if not funds else None
            ),
            confidence=0.94,
        )
    if any(marker in text for marker in ("申购", "赎回", "交易状态", "开放购买", "能买吗")):
        return IntentDecision(
            intent=Intent.FUND_STATUS,
            entities=funds or [EntityCandidate(entity_type="fund", query=_clean_subject(text))],
            confidence=0.96,
        )
    if any(marker in text for marker in ("搜索", "查找", "有哪些", "找基金")):
        entities = [
            EntityCandidate(entity_type="fund_query", query=_clean_subject(text))
        ]
        if index is not None:
            entities.append(index)
        return IntentDecision(
            intent=Intent.FUND_SEARCH,
            entities=entities,
            confidence=0.95,
        )
    if funds or any(marker in text for marker in ("基金", "ETF", "分析", "怎么看")):
        return IntentDecision(
            intent=Intent.FUND_ANALYSIS,
            entities=funds or [EntityCandidate(entity_type="fund", query=_clean_subject(text))],
            confidence=0.86,
        )
    if index:
        return IntentDecision(
            intent=Intent.INDEX_VALUATION,
            entities=[index],
            confidence=0.8,
        )
    return IntentDecision(
        intent=Intent.UNSUPPORTED,
        needs_clarification=True,
        clarification_question="请说明要搜索、分析或估值的基金/指数，并尽量提供代码。",
        confidence=0.5,
    )


class IntentClassifier:
    def __init__(
        self,
        config: AppConfig | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self._config = config or get_config()
        self._llm = llm

    async def classify(self, query: str) -> IntentDecision:
        rule_decision = classify_by_rules(query)
        if (
            rule_decision.intent != Intent.UNSUPPORTED
            or not self._config.agent.use_llm_for_intent
            or self._llm is None
        ):
            return rule_decision

        raw = await asyncio.to_thread(
            self._llm.complete_json,
            [
                system(INTENT_CLASSIFIER_SYSTEM_PROMPT),
                user(query),
            ],
            max_tokens=512,
            temperature=0,
        )
        return IntentDecision.model_validate(_normalize_llm_decision(raw))


def _normalize_llm_decision(raw: dict[str, Any]) -> dict[str, Any]:
    raw.setdefault("entities", [])
    raw.setdefault("needs_clarification", False)
    raw.setdefault("clarification_question", None)
    raw.setdefault("confidence", 0.5)
    return raw
