"""AKShare-backed ETF share and margin provider functions."""

from __future__ import annotations

from typing import Any

import pandas as pd

from .funds import _require_supported_akshare


class AKShareETFProvider:
    """Thin provider wrapper around exchange ETF and margin interfaces."""

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

    def etf_scale_sse(self, date: str) -> pd.DataFrame:
        return self.ak_module.fund_etf_scale_sse(date=date)

    def margin_detail_sse(self, date: str) -> pd.DataFrame:
        return self.ak_module.stock_margin_detail_sse(date=date)

    def margin_detail_szse(self, date: str) -> pd.DataFrame:
        return self.ak_module.stock_margin_detail_szse(date=date)

    def index_constituents(self, symbol: str) -> pd.DataFrame:
        return self.ak_module.index_stock_cons_csindex(symbol=symbol)
