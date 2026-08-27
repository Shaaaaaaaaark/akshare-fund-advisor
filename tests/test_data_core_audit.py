from __future__ import annotations

import sys
from types import SimpleNamespace

import pandas as pd
import pytest

from fund_advisor_data_core.audit import (
    SUPPORTED_AKSHARE_VERSION,
    AuditBundle,
    frame_fingerprint,
)
from fund_advisor_data_core.errors import DataCoreError
from fund_advisor_data_core.providers.akshare import AKShareFundProvider
from fund_advisor_data_core.services import FundSearchService


def _frame() -> pd.DataFrame:
    return pd.DataFrame({"基金代码": ["000001", "000002"], "基金简称": ["甲", "乙"]})


def test_frame_fingerprint_detects_column_rename_and_reorder() -> None:
    frame = _frame()
    renamed = frame.rename(columns={"基金简称": "基金名称"})
    reordered = frame[["基金简称", "基金代码"]]

    assert frame_fingerprint(renamed) != frame_fingerprint(frame)
    assert frame_fingerprint(reordered) != frame_fingerprint(frame)


def test_frame_fingerprint_ignores_row_index_but_tracks_values() -> None:
    frame = _frame()
    reindexed = frame.copy()
    reindexed.index = [7, 9]
    changed = frame.copy()
    changed.loc[0, "基金简称"] = "丙"

    assert frame_fingerprint(reindexed) == frame_fingerprint(frame)
    assert frame_fingerprint(changed) != frame_fingerprint(frame)
    assert frame_fingerprint(frame.iloc[::-1]) != frame_fingerprint(frame)


def test_add_source_requires_explicit_provider_version() -> None:
    bundle = AuditBundle()

    with pytest.raises(TypeError):
        bundle.add_source("fund_name_em", "东方财富-基金基本信息")  # type: ignore[call-arg]

    bundle.add_source(
        "fund_name_em",
        "东方财富-基金基本信息",
        provider_version="1.2.3-runtime",
    )
    assert bundle.sources[0]["provider_version"] == "1.2.3-runtime"


def test_provider_rejects_unlocked_akshare_version(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace(__version__="1.99.0"))

    with pytest.raises(DataCoreError) as excinfo:
        _ = AKShareFundProvider().ak_module

    assert excinfo.value.code == "AKSHARE_VERSION_MISMATCH"
    assert excinfo.value.details["expected"] == SUPPORTED_AKSHARE_VERSION
    assert excinfo.value.details["actual"] == "1.99.0"


def test_provider_accepts_locked_akshare_version(monkeypatch: pytest.MonkeyPatch) -> None:
    locked = SimpleNamespace(__version__=SUPPORTED_AKSHARE_VERSION)
    monkeypatch.setitem(sys.modules, "akshare", locked)

    provider = AKShareFundProvider()

    assert provider.ak_module is locked
    assert provider.provider_version == SUPPORTED_AKSHARE_VERSION


def test_version_mismatch_surfaces_as_non_retryable_failed_audit(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setitem(sys.modules, "akshare", SimpleNamespace(__version__="1.99.0"))

    envelope = FundSearchService(AKShareFundProvider()).search("沪深", limit=5)

    assert envelope.ok is False
    assert envelope.data is None
    assert envelope.error is not None
    assert envelope.error.code == "AKSHARE_VERSION_MISMATCH"
    assert envelope.error.retryable is False
    assert envelope.data_audit[0]["validation"] == "failed"
    assert envelope.data_audit[0]["error"]["code"] == "AKSHARE_VERSION_MISMATCH"
