package com.fundadvisor.web.interaction;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Arrays;

public enum PanelInteractionKind {
    HOT_POLL("hot_poll"),
    FEEDBACK("feedback"),
    FEATURE_VOTE("feature_vote");

    private final String value;

    PanelInteractionKind(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }

    @JsonCreator
    public static PanelInteractionKind fromValue(String value) {
        return Arrays.stream(values())
                .filter(kind -> kind.value.equals(value))
                .findFirst()
                .orElseThrow(() -> new IllegalArgumentException("unsupported interaction kind"));
    }
}
