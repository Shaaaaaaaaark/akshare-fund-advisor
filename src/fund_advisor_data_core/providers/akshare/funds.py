"""AKShare-backed fund provider functions."""

from __future__ import annotations

from typing import Any

import pandas as pd


class AKShareFundProvider:
    """Thin provider wrapper around AKShare fund interfaces."""

    def __init__(self, ak_module: Any | None = None) -> None:
        self._ak_module = ak_module

    @property
    def ak_module(self) -> Any:
        if self._ak_module is None:
            import akshare as ak

            self._ak_module = ak
        return self._ak_module

    @property
    def provider_version(self) -> str | None:
        return getattr(self.ak_module, "__version__", None)

    def fund_names(self) -> pd.DataFrame:
        return self.ak_module.fund_name_em()

    def fund_purchases(self) -> pd.DataFrame:
        return self.ak_module.fund_purchase_em()
