package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.databind.JsonNode;

public record IndexRow(
        String index,
        DatasetMeta meta,
        @JsonProperty("pe_ttm") JsonNode peTtm,
        JsonNode pb,
        @JsonProperty("latest_point") JsonNode latestPoint) {}
