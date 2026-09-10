package com.fundadvisor.web.interaction;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fundadvisor.web.web.ApiExceptionHandler;
import java.time.Instant;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class PanelCommentControllerTest {

    private static final String CLIENT_ID = "40c17919-6643-4a29-85db-a3f5e8b41d70";

    private PanelCommentService service;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        service = org.mockito.Mockito.mock(PanelCommentService.class);
        mockMvc = MockMvcBuilders.standaloneSetup(
                        new PanelCommentController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();
    }

    @Test
    void listsAndCreatesAnonymousComments() throws Exception {
        PanelCommentView comment = new PanelCommentView(
                "comment-1",
                "希望增加板块历史走势",
                "访客-ABC1",
                true,
                Instant.parse("2026-09-10T03:00:00Z"));
        when(service.list(CLIENT_ID, "510310", 20))
                .thenReturn(new PanelCommentFeed("510310", 1, List.of(comment)));
        when(service.create(any())).thenReturn(comment);

        mockMvc.perform(get("/api/panel/comments")
                        .param("client_id", CLIENT_ID)
                        .param("fund", "510310"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.count").value(1))
                .andExpect(jsonPath("$.comments[0].visitor_label").value("访客-ABC1"))
                .andExpect(jsonPath("$.comments[0].mine").value(true));

        mockMvc.perform(post("/api/panel/comments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "client_id":"40c17919-6643-4a29-85db-a3f5e8b41d70",
                                  "fund":"510310",
                                  "content":"希望增加板块历史走势"
                                }
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.content").value("希望增加板块历史走势"));

        verify(service).list(CLIENT_ID, "510310", 20);
        verify(service).create(any());
    }

    @Test
    void rejectsInvalidCommentBody() throws Exception {
        mockMvc.perform(post("/api/panel/comments")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {
                                  "client_id":"not-a-uuid",
                                  "fund":"510310",
                                  "content":"x"
                                }
                                """))
                .andExpect(status().isBadRequest());
    }
}
