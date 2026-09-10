"""AKShare-backed market overview provider functions."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .funds import _require_supported_akshare


class AKShareMarketProvider:
    """Thin provider wrapper around AKShare market interfaces."""

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

    def industry_summary(self) -> pd.DataFrame:
        return self.ak_module.stock_board_industry_summary_ths()
