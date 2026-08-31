package com.fundadvisor.web.interaction;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

public record PanelTopicSummary(
        Map<String, Long> counts,
        @JsonProperty("selected_option") String selectedOption) {}
