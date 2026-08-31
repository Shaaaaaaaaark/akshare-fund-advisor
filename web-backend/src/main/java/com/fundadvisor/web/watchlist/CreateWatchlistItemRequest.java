package com.fundadvisor.web.watchlist;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Size;

public record CreateWatchlistItemRequest(
        @NotNull @JsonProperty("entity_type") EntityType entityType,
        @NotBlank @Size(max = 64) @JsonProperty("entity_code") String entityCode,
        @NotBlank @Size(max = 128) @JsonProperty("display_name") String displayName) {}
