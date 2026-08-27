package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.annotation.JsonInclude;
import com.fasterxml.jackson.annotation.JsonProperty;
import com.fasterxml.jackson.annotation.JsonRawValue;
import java.util.List;

public record DatasetMeta(
        @JsonProperty("as_of") String asOf,
        @JsonProperty("queried_at") String queriedAt,
        DataStatus status,
        @JsonProperty("source_tools") List<String> sourceTools,
        @JsonProperty("audit_refs") List<String> auditRefs,
        @JsonInclude(JsonInclude.Include.NON_NULL) @JsonRawValue String warnings,
        @JsonInclude(JsonInclude.Include.NON_NULL) @JsonRawValue String error) {}
