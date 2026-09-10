package com.fundadvisor.web.dashboard;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fundadvisor.web.config.BffProperties;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;

class DashboardServiceTest {

    private final ObjectMapper mapper = new ObjectMapper();

    @Test
    void rollUpMatchesDashboardSemantics() {
        assertThat(DashboardService.rollUp(List.of())).isEqualTo(DataStatus.UNAVAILABLE);
        assertThat(DashboardService.rollUp(List.of(DataStatus.AVAILABLE, DataStatus.AVAILABLE)))
                .isEqualTo(DataStatus.AVAILABLE);
        assertThat(DashboardService.rollUp(List.of(DataStatus.UNAVAILABLE, DataStatus.UNAVAILABLE)))
                .isEqualTo(DataStatus.UNAVAILABLE);
        assertThat(DashboardService.rollUp(List.of(DataStatus.AVAILABLE, DataStatus.UNAVAILABLE)))
                .isEqualTo(DataStatus.PARTIAL);
        assertThat(DashboardService.rollUp(List.of(DataStatus.AVAILABLE, DataStatus.STALE)))
                .isEqualTo(DataStatus.STALE);
        assertThat(DashboardService.rollUp(List.of(DataStatus.STALE, DataStatus.UNAVAILABLE)))
                .isEqualTo(DataStatus.PARTIAL);
    }

    @Test
    void fundProductPreservesRawEnvelopesAndAuditRefs() {
        DashboardTestSupport.RecordingCaller caller = new DashboardTestSupport.RecordingCaller(mapper);
        String analysisRaw = DashboardTestSupport.rawEnvelope(
                DashboardService.FUND_ANALYZE_TOOL,
                """
                {"analysis":{"data_quality":{"latest_date":"2026-08-18"}},
                 "metrics":{"latest_date":"2026-08-17","return_pct":13.6200001}}
                """);
        String profileRaw = """
                {"schema_version":"1.0","request_id":"profile-request","tool":"fund_profile","ok":true,
                 "data":{"basic_info":{"基金规模":12.3400001}},"sources":[],
                 "data_audit":[{"frame_sha256":"profile-hash"}],"data_warnings":[],
                 "data_policy":{"ai_may_generate_market_data":false},
                 "queried_at":"2026-08-19T01:00:01+08:00","error":null}
                """;
        caller.responses = Map.of(
                DashboardService.FUND_ANALYZE_TOOL,
                analysisRaw,
                DashboardService.FUND_PROFILE_TOOL,
                profileRaw,
                DashboardService.FUND_RATING_TOOL,
                DashboardTestSupport.rawEnvelope(DashboardService.FUND_RATING_TOOL, "{\"ratings\":{\"晨星评级\":5}}"),
                DashboardService.FUND_STATUS_TOOL,
                DashboardTestSupport.rawEnvelope(
                        DashboardService.FUND_STATUS_TOOL,
                        "{\"availability\":{\"source_report_date\":\"2026-08-18\"}}"));
        DashboardService service = service(caller);

        FundProductResponse response = service.fundProduct("000001", 5);

        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(DataStatus.AVAILABLE);
        assertThat(response.sections().analysis().meta().asOf()).isEqualTo("2026-08-18");
        assertThat(response.sections().profile().meta().asOf()).isEmpty();
        assertThat(response.sections().profile().meta().auditRefs()).containsExactly("profile-hash");
        assertThat(response.sections().analysis().envelope()).isEqualTo(analysisRaw);
        assertThat(response.sections().analysis().envelope()).contains("\"return_pct\":13.6200001");
        assertThat(caller.calls)
                .extracting(DashboardTestSupport.Call::tool)
                .containsExactlyInAnyOrder(
                        DashboardService.FUND_ANALYZE_TOOL,
                        DashboardService.FUND_PROFILE_TOOL,
                        DashboardService.FUND_RATING_TOOL,
                        DashboardService.FUND_STATUS_TOOL);
        assertThat(caller.calls.stream()
                        .filter(call -> call.tool().equals(DashboardService.FUND_ANALYZE_TOOL))
                        .findFirst()
                        .orElseThrow()
                        .arguments())
                .containsEntry("years", 5);
    }

    @Test
    void staleBusinessFailureKeepsOriginalErrorAndRollsUp() {
        DashboardTestSupport.RecordingCaller caller = new DashboardTestSupport.RecordingCaller(mapper);
        String staleRaw = """
                {"schema_version":"1.0","request_id":"analysis-stale","tool":"fund_analyze","ok":false,
                 "data":{"metrics":{"latest_date":"2026-07-01","return_pct":1.23456789}},
                 "sources":[],"data_audit":[{"frame_sha256":"stale-hash"}],
                 "data_warnings":[],"data_policy":{"ai_may_generate_market_data":false},
                 "queried_at":"2026-08-19T01:00:00+08:00",
                 "error":{"code":"STALE_OR_INVALID_DATA","message":"stale","retryable":true,"details":{}}}
                """;
        caller.responses = Map.of(
                DashboardService.FUND_ANALYZE_TOOL,
                staleRaw,
                DashboardService.FUND_PROFILE_TOOL,
                DashboardTestSupport.rawEnvelope(DashboardService.FUND_PROFILE_TOOL, "{}"),
                DashboardService.FUND_RATING_TOOL,
                DashboardTestSupport.rawEnvelope(DashboardService.FUND_RATING_TOOL, "{}"),
                DashboardService.FUND_STATUS_TOOL,
                DashboardTestSupport.rawEnvelope(DashboardService.FUND_STATUS_TOOL, "{}"));
        DashboardService service = service(caller);

        FundProductResponse response = service.fundProduct("000001", 3);

        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(DataStatus.STALE);
        assertThat(response.sections().analysis().meta().status()).isEqualTo(DataStatus.STALE);
        assertThat(response.sections().analysis().meta().asOf()).isEqualTo("2026-07-01");
        assertThat(response.sections().analysis().meta().error()).contains("\"code\":\"STALE_OR_INVALID_DATA\"");
        assertThat(response.sections().analysis().envelope()).isEqualTo(staleRaw);
    }

    @Test
    void transportFailureKeepsUpstreamErrorInsteadOfSwallowingIt() {
        DashboardTestSupport.RecordingCaller caller = new DashboardTestSupport.RecordingCaller(mapper);
        caller.failures = Map.of(
                DashboardService.INDEX_VALUATION_TOOL,
                new IllegalStateException("data api index_valuation http 503: upstream down"));
        DashboardService service = service(caller);

        IndexDetail response = service.indexDetail("沪深300", 10, 300);

        assertThat(response).isNotNull();
        assertThat(response.envelope()).isNull();
        assertThat(response.meta().status()).isEqualTo(DataStatus.UNAVAILABLE);
        assertThat(response.meta().asOf()).isEmpty();
        assertThat(response.meta().error())
                .contains("\"code\":\"UPSTREAM_ERROR\"")
                .contains("index_valuation")
                .contains("upstream down");
    }

    @Test
    void transportFailureErrorIsValidJsonForTheFrontend() throws Exception {
        DashboardTestSupport.RecordingCaller caller = new DashboardTestSupport.RecordingCaller(mapper);
        caller.failures = Map.of(
                DashboardService.FUND_ANALYZE_TOOL,
                new IllegalStateException("timeout \"quoted\" 中文"));
        DashboardService service = service(caller);

        FundProductResponse response = service.fundProduct("000001", 3);

        assertThat(response).isNotNull();
        assertThat(response.status()).isEqualTo(DataStatus.PARTIAL);
        JsonNode error = mapper.readTree(response.sections().analysis().meta().error());
        assertThat(error.get("code").asText()).isEqualTo("UPSTREAM_ERROR");
        assertThat(error.get("message").asText()).contains("timeout \"quoted\" 中文");
        assertThat(error.get("retryable").asBoolean()).isTrue();
    }

    @Test
    void stockDetailPreservesEnvelopeAndLatestDate() {
        DashboardTestSupport.RecordingCaller caller = new DashboardTestSupport.RecordingCaller(mapper);
        String stockRaw = DashboardTestSupport.rawEnvelope(
                DashboardService.STOCK_VALUATION_TOOL,
                "{\"lookback\":{\"latest_date\":\"2026-08-18\"},"
                        + "\"summary\":{\"stock_price\":{\"current\":1420.00001}}}");
        caller.responses = Map.of(DashboardService.STOCK_VALUATION_TOOL, stockRaw);
        DashboardService service = service(caller);

        StockDetail response = service.stockDetail("600519", 5, 300);

        assertThat(response).isNotNull();
        assertThat(response.meta().asOf()).isEqualTo("2026-08-18");
        assertThat(response.envelope()).isEqualTo(stockRaw);
        assertThat(response.envelope()).contains("\"current\":1420.00001");
    }

    @Test
    void marketPulsePreservesSnapshotAndAuditMetadata() {
        DashboardTestSupport.RecordingCaller caller = new DashboardTestSupport.RecordingCaller(mapper);
        String raw = DashboardTestSupport.rawEnvelope(
                DashboardService.MARKET_PULSE_TOOL,
                """
                {"market":"A股","snapshot_at":"2026-09-10T09:35:00+08:00",
                 "sectors":[{"rank":1,"name":"银行","change_pct":1.38}],
                 "poll_topics":[]}
                """);
        caller.responses = Map.of(DashboardService.MARKET_PULSE_TOOL, raw);
        DashboardService service = service(caller);

        BoardDetail response = service.marketPulse();

        assertThat(response.board()).isEqualTo("market-pulse");
        assertThat(response.meta().status()).isEqualTo(DataStatus.AVAILABLE);
        assertThat(response.meta().asOf()).isEqualTo("2026-09-10T09:35:00+08:00");
        assertThat(response.envelope()).isEqualTo(raw);
    }

    @Test
    void indexAggregationSubmitsCallsInConfiguredBatches() {
        AtomicInteger active = new AtomicInteger();
        AtomicInteger maximum = new AtomicInteger();
        var caller = new com.fundadvisor.web.dataapi.DashboardToolCaller() {
            @Override
            public com.fundadvisor.web.facts.ToolEnvelope callTool(
                    String tool,
                    Map<String, Object> arguments) {
                int current = active.incrementAndGet();
                maximum.accumulateAndGet(current, Math::max);
                try {
                    Thread.sleep(25);
                    return DashboardTestSupport.envelope(
                            mapper,
                            DashboardTestSupport.rawEnvelope(tool, "{}"));
                } catch (InterruptedException exc) {
                    Thread.currentThread().interrupt();
                    throw new IllegalStateException(exc);
                } finally {
                    active.decrementAndGet();
                }
            }
        };
        BffProperties properties = new BffProperties(
                "http://data-api",
                "http://agent-api",
                Path.of("web/dist"),
                List.of("a", "b", "c", "d", "e"),
                10,
                2,
                Duration.ofSeconds(90),
                new BffProperties.OverviewTargets("a", "510310", "000001", "600519"));

        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            IndicesResponse response = new DashboardService(caller, mapper, properties, executor).indices();

            assertThat(response.rows()).hasSize(5);
            assertThat(maximum).hasValueLessThanOrEqualTo(2);
        }
    }

    private DashboardService service(DashboardTestSupport.RecordingCaller caller) {
        return new DashboardService(
                caller,
                mapper,
                DashboardTestSupport.properties(),
                DashboardTestSupport.DIRECT_EXECUTOR);
    }
}
