package com.fundadvisor.web.watchlist;

import com.fasterxml.jackson.annotation.JsonCreator;
import com.fasterxml.jackson.annotation.JsonValue;
import java.util.Locale;

public enum EntityType {
    INDEX,
    ETF,
    FUND,
    STOCK;

    @JsonCreator
    public static EntityType fromValue(String value) {
        if (value == null || value.isBlank()) {
            throw new IllegalArgumentException("entity_type is required");
        }
        try {
            return valueOf(value.trim().toUpperCase(Locale.ROOT));
        } catch (IllegalArgumentException exc) {
            throw new IllegalArgumentException("entity_type must be index, etf, fund or stock", exc);
        }
    }

    @JsonValue
    public String value() {
        return name().toLowerCase(Locale.ROOT);
    }
}
