"""Evidence-gated report generation."""

from .adapters import document_hit_to_evidence, tool_envelope_to_evidence
from .claims import build_claims
from .gate import EvidenceGate
from .models import (
    ClaimRecord,
    EvidenceRecord,
    GateDecision,
    ResearchReport,
)
from .renderer import render_report
from .response_validator import ResponseValidationError, ResponseValidator

__all__ = [
    "ClaimRecord",
    "EvidenceGate",
    "EvidenceRecord",
    "GateDecision",
    "ResearchReport",
    "ResponseValidationError",
    "ResponseValidator",
    "build_claims",
    "document_hit_to_evidence",
    "render_report",
    "tool_envelope_to_evidence",
]
