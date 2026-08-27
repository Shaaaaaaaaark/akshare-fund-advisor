package com.fundadvisor.web.dataapi;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fundadvisor.web.config.BffProperties;
import com.fundadvisor.web.facts.ToolEnvelope;
import io.github.resilience4j.bulkhead.Bulkhead;
import io.github.resilience4j.bulkhead.BulkheadConfig;
import io.github.resilience4j.reactor.bulkhead.operator.BulkheadOperator;
import java.net.URI;
import java.time.Duration;
import java.util.Map;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.util.UriBuilder;
import reactor.core.publisher.Mono;

@Component
public class DataApiClient implements DashboardToolCaller {

    private final WebClient webClient;
    private final ObjectMapper mapper;
    private final Bulkhead bulkhead;
    private final Duration timeout;

    public DataApiClient(BffProperties properties, WebClient.Builder builder, ObjectMapper mapper) {
        this.webClient = builder.baseUrl(properties.dataApiUrl()).build();
        this.mapper = mapper;
        this.bulkhead = Bulkhead.of(
                "dashboard-data-api",
                BulkheadConfig.custom()
                        .maxConcurrentCalls(properties.concurrency())
                        .maxWaitDuration(Duration.ofMinutes(5))
                        .build());
        this.timeout = properties.dataTimeout();
    }

    @Override
    public Mono<ToolEnvelope> callTool(String tool, Map<String, Object> arguments) {
        return webClient
                .get()
                .uri(uriBuilder -> route(uriBuilder, tool, arguments))
                .accept(MediaType.APPLICATION_JSON)
                .exchangeToMono(response -> response.bodyToMono(String.class)
                        .defaultIfEmpty("")
                        .flatMap(body -> decode(tool, response.statusCode(), body)))
                .timeout(timeout)
                .transformDeferred(BulkheadOperator.of(bulkhead));
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

    private Mono<ToolEnvelope> decode(String tool, HttpStatusCode status, String body) {
        if (!status.is2xxSuccessful()) {
            return Mono.error(new IllegalStateException(
                    "data api " + tool + " http " + status.value() + ": " + truncate(body, 200)));
        }
        try {
            return Mono.just(ToolEnvelope.parse(body, mapper));
        } catch (JsonProcessingException | IllegalArgumentException exc) {
            return Mono.error(new IllegalStateException("decode data api " + tool + " envelope", exc));
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
