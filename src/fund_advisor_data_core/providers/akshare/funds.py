"""AKShare-backed fund provider functions."""

from __future__ import annotations

from typing import Any

import pandas as pd

from fund_advisor_data_core.audit import SUPPORTED_AKSHARE_VERSION
from fund_advisor_data_core.errors import DataCoreError


class AKShareFundProvider:
    """Thin provider wrapper around AKShare fund interfaces."""

    def __init__(self, ak_module: Any | None = None) -> None:
        self._ak_module = ak_module

    @property
    def ak_module(self) -> Any:
        if self._ak_module is None:
            import akshare as ak

            _require_supported_akshare(ak)
            self._ak_module = ak
        return self._ak_module

    @property
    def provider_version(self) -> str | None:
        return getattr(self.ak_module, "__version__", None)

    def fund_names(self) -> pd.DataFrame:
        return self.ak_module.fund_name_em()

    def fund_purchases(self) -> pd.DataFrame:
        return self.ak_module.fund_purchase_em()


def _require_supported_akshare(module: Any) -> None:
    """锁定 AKShare 版本，避免上游字段漂移被当成通过校验的可信数据。"""
    actual_version = getattr(module, "__version__", None)
    if actual_version != SUPPORTED_AKSHARE_VERSION:
        raise DataCoreError(
            "AKSHARE_VERSION_MISMATCH",
            "AKShare 版本未经本项目验证，拒绝继续以避免字段错位",
            {
                "expected": SUPPORTED_AKSHARE_VERSION,
                "actual": actual_version,
            },
        )
