package com.fundadvisor.web.agent;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.asyncDispatch;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.request;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

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
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class AgentProxyHandlerTest {

    private MockWebServer server;
    private MockMvc mockMvc;

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
        AgentProxyHandler handler = new AgentProxyHandler(properties);
        mockMvc = MockMvcBuilders.standaloneSetup(handler).build();
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

        MvcResult pending = mockMvc.perform(post("/api/chat/stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"分析 000001\",\"session_id\":null}"))
                .andExpect(request().asyncStarted())
                .andReturn();
        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Accel-Buffering", "no"))
                .andExpect(content().string(org.hamcrest.Matchers.containsString("event: status")));

        RecordedRequest request = server.takeRequest();
        assertThat(request.getPath()).isEqualTo("/api/chat/stream");
        assertThat(request.getBody().readUtf8()).contains("分析 000001");
    }

    @Test
    void sseBufferingHeadersOverrideUpstreamValuesInsteadOfDuplicating() throws Exception {
        server.enqueue(new MockResponse()
                .setHeader("Content-Type", "text/event-stream")
                .setHeader("X-Accel-Buffering", "no")
                .setHeader("Cache-Control", "no-cache")
                .setBody("event: done\ndata: {}\n\n"));

        MvcResult pending = mockMvc.perform(post("/api/chat/stream")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"message\":\"hi\",\"session_id\":null}"))
                .andExpect(request().asyncStarted())
                .andReturn();
        mockMvc.perform(asyncDispatch(pending))
                .andExpect(status().isOk())
                .andExpect(header().string("X-Accel-Buffering", "no"))
                .andExpect(header().string("Cache-Control", "no-cache"));
    }

    private static String stripTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
