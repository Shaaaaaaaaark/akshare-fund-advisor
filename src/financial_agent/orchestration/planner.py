"""Deterministic intent-to-tool planning."""

from __future__ import annotations

from financial_agent.domain import EntityCandidate, Intent, ToolPlanItem


def build_tool_plan(
    intent: Intent,
    entities: list[EntityCandidate],
) -> list[ToolPlanItem]:
    if intent in {Intent.DOCUMENT_QA, Intent.UNSUPPORTED}:
        return []

    if intent == Intent.FUND_SEARCH:
        plan = [
            ToolPlanItem(
                tool="fund_search",
                arguments={"query": _first_query(entities), "limit": 10},
                reason="根据用户关键词查询真实基金目录",
            )
        ]
        index = next(
            (item for item in entities if item.entity_type == "index"),
            None,
        )
        if index is not None:
            plan.append(
                ToolPlanItem(
                    tool="index_valuation",
                    arguments={
                        "index": index.query,
                        "years": 10,
                        "max_points": 600,
                    },
                    reason="基金搜索主题对应支持的指数，同时取得估值与点位曲线",
                )
            )
        return plan
    if intent == Intent.FUND_STATUS:
        return [
            ToolPlanItem(
                tool="fund_status",
                arguments={"fund": _first_query(entities)},
                reason="查询申购赎回或场内交易状态",
            )
        ]
    if intent == Intent.INDEX_VALUATION:
        return [
            ToolPlanItem(
                tool="index_valuation",
                arguments={
                    "index": _first_query(entities),
                    "years": 10,
                    "max_points": 600,
                },
                reason="查询指数 PE TTM 与 PB 历史序列",
            )
        ]
    if intent == Intent.STOCK_VALUATION:
        return [
            ToolPlanItem(
                tool="stock_valuation",
                arguments={
                    "stock": _first_query(entities),
                    "years": 10,
                    "max_points": 600,
                },
                reason="查询个股历史 PE TTM、PB 与前复权股价曲线",
            )
        ]
    if intent == Intent.FUND_COMPARE:
        return [
            ToolPlanItem(
                tool="fund_compare",
                arguments={
                    "funds": [item.query for item in entities][:5],
                    "years": 3,
                },
                reason="按相同观察窗口比较多只基金",
            )
        ]
    if intent in {
        Intent.FUND_ANALYSIS,
        Intent.DCA_REFERENCE,
        Intent.SELL_OR_REBALANCE,
    }:
        entity = entities[0] if entities else None
        if entity is not None and entity.entity_type == "index":
            return [
                ToolPlanItem(
                    tool="index_valuation",
                    arguments={
                        "index": entity.query,
                        "years": 10,
                        "max_points": 600,
                    },
                    reason="定投问题涉及指数估值，必须先取得真实 PE/PB",
                )
            ]
        return [
            ToolPlanItem(
                tool="fund_analyze",
                arguments={"fund": _first_query(entities), "years": 3},
                reason="取得基金历史指标、状态与可用指数估值",
            )
        ]
    raise ValueError(f"未注册的意图：{intent}")


def _first_query(entities: list[EntityCandidate]) -> str:
    if not entities or not entities[0].query.strip():
        raise ValueError("工具规划缺少实体")
    return entities[0].query.strip()
