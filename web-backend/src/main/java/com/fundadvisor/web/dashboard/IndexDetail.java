package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.annotation.JsonRawValue;

public record IndexDetail(String index, DatasetMeta meta, @JsonRawValue String envelope) {}
