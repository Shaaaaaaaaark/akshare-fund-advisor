package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fundadvisor.web.config.BffProperties;
import com.fundadvisor.web.facts.ToolEnvelope;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;
import java.util.concurrent.Executor;

final class DashboardTestSupport {

    static final Executor DIRECT_EXECUTOR = Runnable::run;

    private DashboardTestSupport() {}

    static BffProperties properties() {
        return new BffProperties(
                "http://data-api",
                "http://agent-api",
                Path.of("web/dist"),
                List.of("沪深300"),
                10,
                2,
                Duration.ofSeconds(90),
                new BffProperties.OverviewTargets("沪深300", "510310", "000001", "600519"));
    }

    static ToolEnvelope envelope(ObjectMapper mapper, String rawJson) {
        try {
            return ToolEnvelope.parse(rawJson, mapper);
        } catch (Exception exc) {
            throw new IllegalArgumentException(exc);
        }
    }

    static final class RecordingCaller implements com.fundadvisor.web.dataapi.DashboardToolCaller {
        final ObjectMapper mapper;
        final List<Call> calls = new ArrayList<>();
        Map<String, String> responses = Map.of();
        Map<String, RuntimeException> failures = Map.of();

        RecordingCaller(ObjectMapper mapper) {
            this.mapper = mapper;
        }

        @Override
        public ToolEnvelope callTool(String tool, Map<String, Object> arguments) {
            calls.add(new Call(tool, arguments));
            RuntimeException failure = failures.get(tool);
            if (failure != null) {
                throw failure;
            }
            String raw = responses.getOrDefault(tool, rawEnvelope(tool, "{}"));
            return envelope(mapper, raw);
        }
    }

    record Call(String tool, Map<String, Object> arguments) {}

    static String rawEnvelope(String tool, String data) {
        return """
                {"schema_version":"1.0","request_id":"%s-request","tool":"%s","ok":true,
                 "data":%s,"sources":[],"data_audit":[],"data_warnings":[],
                 "data_policy":{"ai_may_generate_market_data":false},
                 "queried_at":"2026-08-19T01:00:00+08:00","error":null}
                """.formatted(tool, tool, data);
    }
}
