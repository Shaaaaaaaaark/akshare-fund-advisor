package com.fundadvisor.web.dataapi;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fundadvisor.web.config.BffProperties;
import com.fundadvisor.web.facts.ToolEnvelope;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.bulkhead.BulkheadFullException;
import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.Map;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.client.JdkClientHttpRequestFactory;
import org.springframework.stereotype.Component;
import org.springframework.util.StreamUtils;
import org.springframework.web.client.RestClient;
import org.springframework.web.util.UriBuilder;

@Component
public class DataApiClient implements DashboardToolCaller {

    private final RestClient restClient;
    private final ObjectMapper mapper;
    private final Bulkhead bulkhead;

    public DataApiClient(BffProperties properties, RestClient.Builder builder, ObjectMapper mapper) {
        HttpClient httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(5))
                .build();
        JdkClientHttpRequestFactory requestFactory = new JdkClientHttpRequestFactory(httpClient);
        requestFactory.setReadTimeout(properties.dataTimeout());
        this.restClient = builder
                .baseUrl(properties.dataApiUrl())
                .requestFactory(requestFactory)
                .build();
        this.mapper = mapper;
        this.bulkhead = Bulkhead.of(
                "dashboard-data-api",
                BulkheadConfig.custom()
                        .maxConcurrentCalls(properties.concurrency())
                        .maxWaitDuration(Duration.ZERO)
                        .build());
    }

    @Override
    public ToolEnvelope callTool(String tool, Map<String, Object> arguments) {
        try {
            return Bulkhead.decorateSupplier(bulkhead, () -> restClient
                        .get()
                        .uri(uriBuilder -> route(uriBuilder, tool, arguments))
                        .accept(MediaType.APPLICATION_JSON)
                        .exchange((request, response) -> decode(
                                tool,
                                response.getStatusCode(),
                                StreamUtils.copyToString(response.getBody(), StandardCharsets.UTF_8))))
                    .get();
        } catch (BulkheadFullException exc) {
            throw new IllegalStateException(
                    "data api " + tool + " UPSTREAM_ERROR: concurrency limit reached",
                    exc);
        }
    }

    URI route(UriBuilder builder, String tool, Map<String, Object> arguments) {
        return switch (tool) {
            case "fund_search" -> builder.path("/v1/funds/search")
                    .queryParam("query", stringArgument(arguments, "query"))
                    .queryParam("limit", intArgument(arguments, "limit", 10))
                    .build();
            case "etf_dashboard" -> builder.path("/v1/etfs/{fund}")
                    .queryParam("years", intArgument(arguments, "years", 3))
                    .queryParam("max_points", intArgument(arguments, "max_points", 600))
                    .build(stringArgument(arguments, "fund"));
            case "fund_analyze" -> builder.path("/v1/funds/{fund}/analysis")
                    .queryParam("years", intArgument(arguments, "years", 3))
                    .build(stringArgument(arguments, "fund"));
            case "fund_profile" -> builder.path("/v1/funds/{fund}/profile")
                    .build(stringArgument(arguments, "fund"));
            case "fund_rating" -> builder.path("/v1/funds/{fund}/rating")
                    .build(stringArgument(arguments, "fund"));
            case "fund_status" -> builder.path("/v1/funds/{fund}/status")
                    .build(stringArgument(arguments, "fund"));
            case "qdii_purchase_board" -> builder.path("/v1/boards/qdii-purchase").build();
            case "market_pulse" -> builder.path("/v1/markets/hot-sectors").build();
            case "index_valuation" -> builder.path("/v1/indices/{index}")
                    .queryParam("years", intArgument(arguments, "years", 10))
                    .queryParam("max_points", intArgument(arguments, "max_points", 600))
                    .build(stringArgument(arguments, "index"));
            case "stock_valuation" -> builder.path("/v1/stocks/{stock}")
                    .queryParam("years", intArgument(arguments, "years", 10))
                    .queryParam("max_points", intArgument(arguments, "max_points", 600))
                    .build(stringArgument(arguments, "stock"));
            default -> throw new IllegalArgumentException("unsupported dashboard data operation " + tool);
        };
    }

    private ToolEnvelope decode(String tool, HttpStatusCode status, String body) throws IOException {
        if (!status.is2xxSuccessful()) {
            throw new IllegalStateException(
                    "data api " + tool + " http " + status.value() + ": " + truncate(body, 200));
        }
        try {
            return ToolEnvelope.parse(body, mapper);
        } catch (JsonProcessingException | IllegalArgumentException exc) {
            throw new IllegalStateException("decode data api " + tool + " envelope", exc);
        }
    }

    private String stringArgument(Map<String, Object> arguments, String key) {
        Object value = arguments.get(key);
        if (!(value instanceof String text) || text.isBlank()) {
            throw new IllegalArgumentException("data api argument " + key + " is required");
        }
        return text;
    }

    private int intArgument(Map<String, Object> arguments, String key, int fallback) {
        Object value = arguments.get(key);
        if (value instanceof Number number) {
            return number.intValue();
        }
        return fallback;
    }

    private String truncate(String body, int limit) {
        if (body.length() <= limit) {
            return body;
        }
        return body.substring(0, limit);
    }
}
