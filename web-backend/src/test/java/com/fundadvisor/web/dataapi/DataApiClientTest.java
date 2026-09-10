package com.fundadvisor.web.dataapi;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fundadvisor.web.config.BffProperties;
import com.fundadvisor.web.facts.ToolEnvelope;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import java.util.Map;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.Future;
import java.util.concurrent.TimeUnit;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.client.RestClient;

class DataApiClientTest {

    private MockWebServer server;
    private DataApiClient client;

    @BeforeEach
    void setUp() throws Exception {
        server = new MockWebServer();
        server.start();
        BffProperties properties = new BffProperties(
                stripTrailingSlash(server.url("/").toString()),
                "http://agent-api",
                Path.of("web/dist"),
                List.of("沪深300"),
                10,
                2,
                Duration.ofSeconds(3),
                new BffProperties.OverviewTargets("沪深300", "510310", "000001", "600519"));
        client = new DataApiClient(properties, RestClient.builder(), new ObjectMapper());
    }

    @AfterEach
    void tearDown() throws Exception {
        server.shutdown();
    }

    @Test
    void callToolMapsIndexValuationToRestAndKeepsRawEnvelope() throws Exception {
        server.enqueue(new MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody("""
                        {"schema_version":"1.0",
                         "request_id":"7d9b9c4f-b2b4-4a25-8137-4a24c4634f68",
                         "tool":"index_valuation","ok":true,
                         "data":{"summary":{"pe_ttm":{"current":13.6200001}}},
                         "sources":[],"data_audit":[{"frame_sha256":"audit-hash"}],
                         "data_warnings":[],"data_policy":{"ai_may_generate_market_data":false},
                         "queried_at":"2026-08-18T00:00:00+08:00","error":null}
                        """));

        ToolEnvelope envelope = client.callTool(
                "index_valuation",
                Map.of("index", "沪深300", "years", 10, "max_points", 600));

        RecordedRequest request = server.takeRequest();
        String decodedPath = URLDecoder.decode(request.getPath(), StandardCharsets.UTF_8);
        assertThat(decodedPath).startsWith("/v1/indices/沪深300?");
        assertThat(decodedPath).contains("years=10");
        assertThat(decodedPath).contains("max_points=600");
        assertThat(envelope).isNotNull();
        assertThat(envelope.ok()).isTrue();
        assertThat(envelope.rawJson()).contains("\"request_id\":\"7d9b9c4f-b2b4-4a25-8137-4a24c4634f68\"");
        assertThat(envelope.rawJson()).contains("\"current\":13.6200001");
        assertThat(envelope.frameHashes()).containsExactly("audit-hash");
    }

    @Test
    void routeMapsFundProductOperations() {
        assertRoute(
                "fund_analyze",
                Map.of("fund", "000001", "years", 5),
                "/v1/funds/000001/analysis",
                "years=5");
        assertRoute("fund_profile", Map.of("fund", "000001"), "/v1/funds/000001/profile", "");
        assertRoute("fund_rating", Map.of("fund", "000001"), "/v1/funds/000001/rating", "");
        assertRoute("fund_status", Map.of("fund", "000001"), "/v1/funds/000001/status", "");
        assertRoute("market_pulse", Map.of(), "/v1/markets/hot-sectors", "");
    }

    @Test
    void rejectsUnknownTool() {
        assertThatThrownBy(() -> client.callTool("unknown_operation", Map.of()))
                .hasMessageContaining("unsupported dashboard data operation");
    }

    @Test
    void invalidArgumentsFailBeforeCallingTheDataApi() {
        assertThatThrownBy(() -> client.callTool("fund_search", Map.of("limit", 5)))
                .isInstanceOf(IllegalArgumentException.class)
                .hasMessageContaining("data api argument query is required");
    }

    @Test
    void bulkheadRejectsImmediatelyInsteadOfQueuingRequests() throws Exception {
        BffProperties singleSlot = new BffProperties(
                stripTrailingSlash(server.url("/").toString()),
                "http://agent-api",
                Path.of("web/dist"),
                List.of("沪深300"),
                10,
                1,
                Duration.ofSeconds(3),
                new BffProperties.OverviewTargets("沪深300", "510310", "000001", "600519"));
        DataApiClient limited = new DataApiClient(singleSlot, RestClient.builder(), new ObjectMapper());
        server.enqueue(new MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody(DashboardRawEnvelopes.raw("fund_profile"))
                .setBodyDelay(1, TimeUnit.SECONDS));

        try (ExecutorService executor = Executors.newVirtualThreadPerTaskExecutor()) {
            Future<ToolEnvelope> first =
                    executor.submit(() -> limited.callTool("fund_profile", Map.of("fund", "000001")));
            assertThat(server.takeRequest(3, TimeUnit.SECONDS)).isNotNull();

            long start = System.nanoTime();
            assertThatThrownBy(() -> limited.callTool("fund_profile", Map.of("fund", "000001")))
                    .isInstanceOf(IllegalStateException.class)
                    .hasMessageContaining("UPSTREAM_ERROR");
            long elapsedMillis = Duration.ofNanos(System.nanoTime() - start).toMillis();

            assertThat(elapsedMillis).isLessThan(1000L);
            assertThat(first.get(3, TimeUnit.SECONDS)).isNotNull();
        }
    }

    private void assertRoute(String tool, Map<String, Object> arguments, String path, String query) {
        server.enqueue(new MockResponse()
                .setHeader("Content-Type", "application/json")
                .setBody(DashboardRawEnvelopes.raw(tool)));

        client.callTool(tool, arguments);

        try {
            String actual = URLDecoder.decode(server.takeRequest().getPath(), StandardCharsets.UTF_8);
            String expected = query.isEmpty() ? path : path + "?" + query;
            assertThat(actual).isEqualTo(expected);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new AssertionError(exc);
        }
    }

    private static String stripTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }

    private static final class DashboardRawEnvelopes {
        static String raw(String tool) {
            return """
                    {"schema_version":"1.0","request_id":"%s-request","tool":"%s","ok":true,
                     "data":{},"sources":[],"data_audit":[],"data_warnings":[],
                     "data_policy":{"ai_may_generate_market_data":false},
                     "queried_at":"2026-08-19T01:00:00+08:00","error":null}
                    """.formatted(tool, tool);
        }
    }
}
