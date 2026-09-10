package com.fundadvisor.web.interaction;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

public record PanelCommentView(
        String id,
        String content,
        @JsonProperty("visitor_label") String visitorLabel,
        boolean mine,
        @JsonProperty("created_at") Instant createdAt) {}
