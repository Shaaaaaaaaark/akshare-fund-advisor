package com.fundadvisor.web.interaction;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.Map;

public record PanelInteractionSummary(
        String fund,
        @JsonProperty("hot_polls") Map<String, PanelTopicSummary> hotPolls,
        PanelTopicSummary feedback,
        @JsonProperty("feature_vote") PanelTopicSummary featureVote) {}
