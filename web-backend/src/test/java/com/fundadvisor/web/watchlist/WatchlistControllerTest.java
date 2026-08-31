package com.fundadvisor.web.watchlist;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
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

class WatchlistControllerTest {

    private WatchlistService service;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        service = org.mockito.Mockito.mock(WatchlistService.class);
        mockMvc = MockMvcBuilders.standaloneSetup(new WatchlistController(service))
                .setControllerAdvice(new ApiExceptionHandler())
                .build();
    }

    @Test
    void listsAndCreatesItems() throws Exception {
        WatchlistItem item = new WatchlistItem(
                "id-1",
                EntityType.STOCK,
                "600519",
                "贵州茅台",
                Instant.parse("2026-08-27T10:00:00Z"));
        when(service.findAll()).thenReturn(List.of(item));
        when(service.create(any())).thenReturn(item);

        mockMvc.perform(get("/api/watchlist"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$[0].entity_type").value("stock"))
                .andExpect(jsonPath("$[0].entity_code").value("600519"));

        mockMvc.perform(post("/api/watchlist")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"entity_type":"stock",
                                 "entity_code":"600519",
                                 "display_name":"贵州茅台"}
                                """))
                .andExpect(status().isCreated())
                .andExpect(jsonPath("$.display_name").value("贵州茅台"));
    }

    @Test
    void rejectsInvalidRequest() throws Exception {
        mockMvc.perform(post("/api/watchlist")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("""
                                {"entity_type":"stock","entity_code":"","display_name":""}
                                """))
                .andExpect(status().isBadRequest())
                .andExpect(jsonPath("$.detail").exists());
    }

    @Test
    void deletesItem() throws Exception {
        mockMvc.perform(delete("/api/watchlist/id-1"))
                .andExpect(status().isNoContent());

        verify(service).delete("id-1");
    }
}
