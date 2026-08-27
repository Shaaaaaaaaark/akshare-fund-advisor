package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.annotation.JsonProperty;

public record OverviewResponse(
        DataStatus status,
        IndexDetail index,
        @JsonProperty("etf") ETFDetail etf,
        FundOverview fund,
        StockDetail stock,
        @JsonProperty("fund_screening") OverviewCapability fundScreening,
        @JsonProperty("stock_screening") OverviewCapability stockScreening) {}
