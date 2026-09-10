package com.fundadvisor.web.interaction;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fundadvisor.web.web.ApiExceptionHandler;
import java.util.List;
import java.util.Map;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class PanelInteractionControllerTest {

    private static final String CLIENT_ID = "40c17919-6643-4a29-85db-a3f5e8b41d70";
    private static final String HOT_POLL_TOPIC = "sector_20260910_012345abcdef";

    private PanelInteractionService service;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        service = org.mockito.Mockito.mock(PanelInteractionService.class);
        mockMvc = MockMvcBuilders.standaloneSetup(
                        new PanelInteractionController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();
    }

    @Test
    void readsAndSubmitsPanelInteractions() throws Exception {
        PanelInteractionSummary summary = new PanelInteractionSummary(
                "510310",
                Map.of(
                        HOT_POLL_TOPIC,
                        new PanelTopicSummary(
                                Map.of("yes", 4L, "no", 2L),
                                "yes")),
                new PanelTopicSummary(Map.of("useful", 1L), null),
                new PanelTopicSummary(Map.of("other", 0L), null));
        when(service.summary(CLIENT_ID, "510310", List.of(HOT_POLL_TOPIC)))
                .thenReturn(summary);
        when(service.submit(any())).thenReturn(summary);

        mockMvc.perform(get("/api/panel/interactions")
                        .param("client_id", CLIENT_ID)
                        .param("fund", "510310")
                        .param("hot_poll_topic", HOT_POLL_TOPIC))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.hot_polls." + HOT_POLL_TOPIC + ".counts.yes").value(4))
                .andExpect(jsonPath("$.hot_polls." + HOT_POLL_TOPIC + ".selected_option").value("yes"));

        mockMvc.perform(post("/api/panel/interactions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "kind":"hot_poll",
                                  "topic_key":"sector_20260910_012345abcdef",
                                  "option_key":"yes",
                                  "client_id":"40c17919-6643-4a29-85db-a3f5e8b41d70",
                                  "fund":"510310"
                                }
                                """))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.fund").value("510310"));

        verify(service).summary(CLIENT_ID, "510310", List.of(HOT_POLL_TOPIC));
        verify(service).submit(any());
    }

    @Test
    void rejectsMalformedClientIdentifier() throws Exception {
        mockMvc.perform(post("/api/panel/interactions")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "kind":"feedback",
                                  "topic_key":"etf_feedback",
                                  "option_key":"useful",
                                  "client_id":"not-a-uuid",
                                  "fund":"510310"
                                }
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").exists());
    }
}
