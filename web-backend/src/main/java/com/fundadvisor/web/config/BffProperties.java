package com.fundadvisor.web.config;

import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public record BffProperties(
        String dataApiUrl,
        String agentApiUrl,
        Path staticDir,
        List<String> indexUniverse,
        int indexYears,
        int concurrency,
        Duration dataTimeout,
        OverviewTargets overview) {

    public static BffProperties fromEnvironment() {
        Map<String, String> env = System.getenv();
        int concurrency = intValue(env, "DASHBOARD_CONCURRENCY", 4);
        if (concurrency < 1) {
            concurrency = 1;
        }
        return new BffProperties(
                stringValue(env, "DATA_API_URL", "http://data-api:8003"),
                stringValue(env, "AGENT_API_URL", "http://agent-api:8000"),
                Path.of(stringValue(env, "WEB_STATIC_DIR", "web/dist")),
                listValue(
                        env,
                        "DASHBOARD_INDEX_UNIVERSE",
                        List.of("沪深300", "中证500", "中证1000", "上证50", "创业板50", "中证800")),
                intValue(env, "DASHBOARD_INDEX_YEARS", 10),
                concurrency,
                Duration.ofSeconds(intValue(env, "DATA_API_TIMEOUT_SECONDS", 90)),
                new OverviewTargets(
                        stringValue(env, "DASHBOARD_OVERVIEW_INDEX", "沪深300"),
                        stringValue(env, "DASHBOARD_OVERVIEW_ETF", "510310"),
                        stringValue(env, "DASHBOARD_OVERVIEW_FUND", "000001"),
                        stringValue(env, "DASHBOARD_OVERVIEW_STOCK", "600519")));
    }

    public Duration singleCallBudget() {
        return dataTimeout.plusSeconds(5);
    }

    public Duration aggregateBudget(int taskCount) {
        int batches = (taskCount + concurrency - 1) / concurrency;
        return dataTimeout.multipliedBy(batches).plusSeconds(5);
    }

    private static String stringValue(Map<String, String> env, String key, String fallback) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            return fallback;
        }
        return value.trim();
    }

    private static int intValue(Map<String, String> env, String key, int fallback) {
        String value = env.get(key);
        if (value == null || value.isBlank()) {
            return fallback;
        }
        try {
            return Integer.parseInt(value.trim());
        } catch (NumberFormatException ignored) {
            return fallback;
        }
    }

    private static List<String> listValue(Map<String, String> env, String key, List<String> fallback) {
        String raw = env.get(key);
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        List<String> values = new ArrayList<>();
        for (String value : raw.split(",")) {
            String trimmed = value.trim();
            if (!trimmed.isEmpty()) {
                values.add(trimmed);
            }
        }
        return values.isEmpty() ? fallback : List.copyOf(values);
    }

    public record OverviewTargets(String index, String etf, String fund, String stock) {}
}
