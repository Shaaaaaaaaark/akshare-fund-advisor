package com.fundadvisor.web.agent;

import static org.assertj.core.api.Assertions.assertThat;

import com.fundadvisor.web.config.BffProperties;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import okhttp3.mockwebserver.MockResponse;
import okhttp3.mockwebserver.MockWebServer;
import okhttp3.mockwebserver.RecordedRequest;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunctions;

class AgentProxyHandlerTest {

    private MockWebServer server;
    private WebTestClient client;

    @BeforeEach
    void setUp() throws Exception {
        server = new MockWebServer();
        server.start();
        BffProperties properties = new BffProperties(
                "http://data-api",
                stripTrailingSlash(server.url("/").toString()),
                Path.of("web/dist"),
                List.of("沪深300"),
                10,
                2,
                Duration.ofSeconds(3),
                new BffProperties.OverviewTargets("沪深300", "510310", "000001", "600519"));
        AgentProxyHandler handler = new AgentProxyHandler(properties, WebClient.builder());
        client = WebTestClient.bindToRouterFunction(RouterFunctions.route()
                        .route(RequestPredicates.path("/api/chat/**"), handler::proxy)
                        .build())
                .build();
    }

    @AfterEach
    void tearDown() throws Exception {
        server.shutdown();
    }

    @Test
    void proxiesAgentSseWithoutChangingPathOrBody() throws Exception {
        server.enqueue(new MockResponse()
                .setHeader("Content-Type", "text/event-stream")
                .setBody("event: status\ndata: {\"message\":\"ok\"}\n\n"));

        client.post()
                .uri("/api/chat/stream")
                .contentType(MediaType.APPLICATION_JSON)
                .bodyValue("{\"message\":\"分析 000001\",\"session_id\":null}")
                .exchange()
                .expectStatus().isOk()
                .expectHeader().valueEquals("X-Accel-Buffering", "no")
                .expectBody(String.class)
                .value(body -> assertThat(body).contains("event: status"));

        RecordedRequest request = server.takeRequest();
        assertThat(request.getPath()).isEqualTo("/api/chat/stream");
        assertThat(request.getBody().readUtf8()).contains("分析 000001");
    }

    private static String stripTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
