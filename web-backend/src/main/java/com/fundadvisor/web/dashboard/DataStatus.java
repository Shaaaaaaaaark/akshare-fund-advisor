package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.annotation.JsonValue;

public enum DataStatus {
    AVAILABLE("available"),
    PARTIAL("partial"),
    STALE("stale"),
    UNAVAILABLE("unavailable"),
    NOT_IMPLEMENTED("not_implemented");

    private final String value;

    DataStatus(String value) {
        this.value = value;
    }

    @JsonValue
    public String value() {
        return value;
    }
}
