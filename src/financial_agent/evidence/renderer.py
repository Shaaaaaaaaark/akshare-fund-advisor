"""Render reports deterministically from allowed Claims and Evidence."""

from __future__ import annotations

import re
from collections.abc import Sequence
from datetime import datetime
from typing import Any
from uuid import UUID

from financial_agent.domain import Intent, TaskStatus

from .models import (
    Citation,
    ClaimRecord,
    EvidenceRecord,
    EvidenceType,
    GateDecision,
    ReportFact,
    ResearchReport,
)

_LABELS = {
    "document_excerpt": "官方文档摘录",
    "summary.pe_ttm.current": "PE TTM 当前值",
    "summary.pe_ttm.percentile": "PE TTM 历史分位",
    "summary.pe_ttm.level": "PE TTM 相对位置",
    "summary.pb.current": "PB 当前值",
    "summary.pb.percentile": "PB 历史分位",
    "summary.pb.level": "PB 相对位置",
    "summary.stock_price.current": "前复权股价",
    "metrics.latest_value": "最新净值或收盘值",
    "metrics.returns_pct.12_month": "近十二个月收益",
    "metrics.current_drawdown_pct": "当前回撤",
    "metrics.max_drawdown_pct": "区间最大回撤",
    "metrics.annualized_volatility_pct": "区间年化波动",
    "metrics.history_position_percentile": "净值历史位置",
    "market_snapshot.premium_rate_pct": "ETF 场内溢价率",
    "availability.mode": "交易渠道",
    "availability.source_report_date": "状态来源日期",
    "availability.latest_nav_or_income": "最新净值或万份收益",
    "availability.off_exchange.subscription_status": "申购状态",
    "availability.off_exchange.redemption_status": "赎回状态",
    "availability.off_exchange.can_submit_subscription": "是否开放申购",
    "availability.off_exchange.can_submit_redemption": "是否开放赎回",
    "availability.exchange.standard_market_open_now": "当前是否在标准交易时段",
    "availability.exchange.can_submit_standard_session_order": "是否可提交标准时段委托",
    "count": "匹配数量",
    "fund.code": "基金代码",
    "fund.name": "基金名称",
    "stock.code": "股票代码",
    "stock.name": "股票名称",
    "index.index_code": "指数代码",
    "index.name": "指数名称",
}

_LEVEL_TEXT = {
    "low": "历史低位",
    "lower_middle": "历史中低位置",
    "middle": "历史中间位置",
    "upper_middle": "历史中高位置",
    "high": "历史高位",
}


def _title(intent: Intent, evidence: Sequence[EvidenceRecord]) -> str:
    named = next((item.subject.name for item in evidence if item.subject.name), None)
    subject = named or next((item.subject.id for item in evidence), "查询对象")
    suffix = {
        Intent.INDEX_VALUATION: "估值研究",
        Intent.STOCK_VALUATION: "个股估值研究",
        Intent.FUND_ANALYSIS: "基金研究",
        Intent.FUND_STATUS: "交易状态",
        Intent.FUND_SEARCH: "搜索结果",
        Intent.FUND_COMPARE: "基金比较",
        Intent.DCA_REFERENCE: "定投条件研究",
        Intent.SELL_OR_REBALANCE: "再平衡条件研究",
        Intent.DOCUMENT_QA: "文档研究",
    }.get(intent, "研究结果")
    return f"{subject} {suffix}"


def _status_for_grade(grade: str) -> TaskStatus:
    if grade in {"A", "B"}:
        return TaskStatus.COMPLETED
    if grade == "C":
        return TaskStatus.PARTIAL_RESULT
    if grade == "D":
        return TaskStatus.CANNOT_CONFIRM
    return TaskStatus.POLICY_BLOCKED


def _label_for(field: str) -> str:
    ordinals = ("一", "二", "三", "四", "五")
    if field in _LABELS:
        return _LABELS[field]
    matched = re.fullmatch(r"results\[(\d+)\]\.(code|name|type)", field)
    if matched:
        names = {"code": "代码", "name": "名称", "type": "类型"}
        index = int(matched.group(1))
        ordinal = ordinals[index] if index < len(ordinals) else "其他"
        return f"候选{ordinal}{names[matched.group(2)]}"
    matched = re.fullmatch(
        r"results\[(\d+)\]\.fund\.(code|name|type)",
        field,
    )
    if matched:
        names = {"code": "代码", "name": "名称", "type": "类型"}
        index = int(matched.group(1))
        ordinal = ordinals[index] if index < len(ordinals) else "其他"
        return f"比较对象{ordinal}{names[matched.group(2)]}"
    return field


def _interpretations(
    facts: Sequence[ReportFact], evidence_map: dict[UUID, EvidenceRecord]
) -> list[str]:
    result: list[str] = []
    for fact in facts:
        record = evidence_map[fact.evidence_id]
        if record.field.endswith(".level") and isinstance(record.value, str):
            text = _LEVEL_TEXT.get(record.value)
            if text:
                metric = "PE TTM" if ".pe_ttm." in record.field else "PB"
                result.append(f"{metric} 位于所选观察窗口的{text}。")
    if any("history_position_percentile" in evidence_map[item.evidence_id].field for item in facts):
        result.append("净值历史位置不等同于指数估值分位，两者没有合并计算。")
    if any(".pe_ttm." in evidence_map[item.evidence_id].field for item in facts) and any(
        ".pb." in evidence_map[item.evidence_id].field for item in facts
    ):
        result.append("PE 与 PB 经济含义不同，本报告分别展示，不生成综合估值分。")
    return result


def render_report(
    *,
    task_id: UUID,
    intent: Intent,
    evidence: Sequence[EvidenceRecord],
    claims: Sequence[ClaimRecord],
    decision: GateDecision,
    generated_at: datetime,
    extra_warnings: Sequence[str] = (),
) -> ResearchReport:
    evidence_map = {item.evidence_id: item for item in evidence}
    facts: list[ReportFact] = []
    for claim in claims:
        if not claim.allowed:
            continue
        record = evidence_map.get(claim.arguments.get("value"))
        if record is None:
            continue
        facts.append(
            ReportFact(
                label=_label_for(record.field),
                value=record.value,
                display_value=record.display_value or str(record.value),
                unit=record.unit,
                as_of=record.as_of,
                evidence_id=record.evidence_id,
            )
        )

    citations: list[Citation] = []
    for record in evidence:
        if record.type != EvidenceType.DOCUMENT_FACT:
            continue
        metadata: dict[str, Any] = record.metadata
        if not metadata.get("url") or not metadata.get("title"):
            continue
        citations.append(
            Citation(
                evidence_id=record.evidence_id,
                title=str(metadata["title"]),
                url=str(metadata["url"]),
                page=metadata.get("page"),
                version=metadata.get("version"),
            )
        )

    warnings = list(dict.fromkeys([*decision.warnings, *extra_warnings]))
    if facts and intent == Intent.DOCUMENT_QA:
        summary = "已检索到可引用的官方文档内容，详见事实与引用。"
    elif facts:
        summary = "；".join(f"{item.label}：{item.display_value}" for item in facts[:6])
    elif decision.grade == "E":
        summary = "该请求超出研究工具的安全边界，未生成投资结论。"
    else:
        summary = "当前证据不足，无法确认。"

    return ResearchReport(
        task_id=task_id,
        status=_status_for_grade(decision.grade).value,
        title=_title(intent, evidence),
        summary=summary,
        facts=facts,
        analysis=_interpretations(facts, evidence_map),
        buy_conditions=(
            ["仅在资金期限、应急资金和目标仓位均已确认后评估分批投入。"]
            if decision.grade in {"A", "B", "C"} and intent == Intent.DCA_REFERENCE
            else []
        ),
        sell_or_rebalance_conditions=(
            ["仅在资金用途、目标仓位或产品逻辑发生变化时重新评估。"]
            if decision.grade in {"A", "B", "C"} and intent == Intent.SELL_OR_REBALANCE
            else []
        ),
        risks=[
            "历史数据和历史分位不预测未来涨跌。",
            "公开数据上游可能延迟或调整口径，应结合报告日期理解。",
        ],
        missing_information=decision.reasons,
        warnings=warnings,
        citations=citations,
        evidence_grade=decision.grade,
        generated_at=generated_at,
    )
