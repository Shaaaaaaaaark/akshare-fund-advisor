package com.fundadvisor.web.interaction;

import com.fasterxml.jackson.annotation.JsonProperty;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

public record SubmitPanelInteractionRequest(
        @JsonProperty("kind") @NotNull PanelInteractionKind kind,
        @JsonProperty("topic_key") @NotBlank @Size(max = 64) String topicKey,
        @JsonProperty("option_key") @NotBlank @Size(max = 64) String optionKey,
        @JsonProperty("client_id")
                @NotBlank
                @Pattern(
                        regexp = "^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}$")
                String clientId,
        @JsonProperty("fund") @NotBlank @Pattern(regexp = "^\\d{6}$") String fund) {}
