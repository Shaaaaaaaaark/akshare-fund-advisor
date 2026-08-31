package com.fundadvisor.web.watchlist;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.time.Instant;

public record WatchlistItem(
        String id,
        @JsonProperty("entity_type") EntityType entityType,
        @JsonProperty("entity_code") String entityCode,
        @JsonProperty("display_name") String displayName,
        @JsonProperty("created_at") Instant createdAt) {}
