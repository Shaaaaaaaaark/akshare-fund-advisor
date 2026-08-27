package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonRawValue;

public record FundOverview(
        String fund,
        DatasetMeta meta,
        @JsonInclude(JsonInclude.Include.NON_NULL) @JsonRawValue String envelope) {}
