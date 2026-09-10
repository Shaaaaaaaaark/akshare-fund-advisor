package com.fundadvisor.web.interaction;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record CreatePanelCommentRequest(
        @JsonProperty("client_id")
                @NotBlank
                @Pattern(
                        regexp = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
                String clientId,
        @JsonProperty("fund") @NotBlank @Pattern(regexp = "^\\d{6}$") String fund,
        @JsonProperty("content") @NotBlank @Size(min = 2, max = 280) String content) {}
