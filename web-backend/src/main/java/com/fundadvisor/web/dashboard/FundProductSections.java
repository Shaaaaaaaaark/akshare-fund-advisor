package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.annotation.JsonProperty;

public record FundProductSections(
        FundProductSection analysis,
        FundProductSection profile,
        FundProductSection rating,
        @JsonProperty("trading_status") FundProductSection tradingStatus) {}
