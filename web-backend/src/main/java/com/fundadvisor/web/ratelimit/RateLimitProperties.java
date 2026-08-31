package com.fundadvisor.web.ratelimit;

import java.time.Duration;
import java.util.Map;

public record RateLimitProperties(boolean enabled, int requests, Duration window) {

    public RateLimitProperties {
        if (requests < 1) {
            throw new IllegalArgumentException("rate limit requests must be positive");
        }
        if (window == null || window.isZero() || window.isNegative()) {
            throw new IllegalArgumentException("rate limit window must be positive");
        }
    }

    public static RateLimitProperties fromEnvironment() {
        Map<String, String> env = System.getenv();
        return new RateLimitProperties(
                booleanValue(env, "DASHBOARD_RATE_LIMIT_ENABLED", true),
                intValue(env, "DASHBOARD_RATE_LIMIT_REQUESTS", 120),
                Duration.ofSeconds(intValue(env, "DASHBOARD_RATE_LIMIT_WINDOW_SECONDS", 60)));
    }

    private static boolean booleanValue(Map<String, String> env, String key, boolean fallback) {
        String raw = env.get(key);
        return raw == null || raw.isBlank() ? fallback : Boolean.parseBoolean(raw.trim());
    }

    private static int intValue(Map<String, String> env, String key, int fallback) {
        String raw = env.get(key);
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        try {
            return Integer.parseInt(raw.trim());
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }
}
