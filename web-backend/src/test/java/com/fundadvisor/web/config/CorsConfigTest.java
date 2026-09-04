package com.fundadvisor.web.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.options;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.header;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import org.junit.jupiter.api.Test;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RestController;
import org.springframework.web.filter.CorsFilter;

class CorsConfigTest {

    @Test
    void preflightAllowsConfiguredOrigin() throws Exception {
        MockMvc mockMvc = mockMvc("https://user.github.io");

        mockMvc.perform(options("/api/dashboard/indices")
                        .header("Origin", "https://user.github.io")
                        .header("Access-Control-Request-Method", "GET"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin", "https://user.github.io"));
    }

    @Test
    void streamingAgentPathIsCovered() throws Exception {
        MockMvc mockMvc = mockMvc("https://user.github.io");

        mockMvc.perform(options("/api/chat/stream")
                        .header("Origin", "https://user.github.io")
                        .header("Access-Control-Request-Method", "POST"))
                .andExpect(status().isOk())
                .andExpect(header().string(
                        "Access-Control-Allow-Origin", "https://user.github.io"));
    }

    @Test
    void disabledWhenNoOriginsConfigured() throws Exception {
        MockMvc mockMvc = mockMvc("");

        mockMvc.perform(get("/api/dashboard/indices")
                        .header("Origin", "https://evil.example.com"))
                .andExpect(header().doesNotExist("Access-Control-Allow-Origin"));
    }

    @Test
    void parsesAndDeduplicatesOrigins() {
        assertThat(CorsConfig.allowedOrigins(
                                " https://user.github.io/, https://api.example.com, https://user.github.io "))
                .containsExactly("https://user.github.io", "https://api.example.com");
    }

    private MockMvc mockMvc(String origins) {
        CorsFilter filter = CorsConfig.corsFilterRegistration(origins).getFilter();
        return MockMvcBuilders.standaloneSetup(new ProbeController())
                .addFilters(filter)
                .build();
    }

    @RestController
    static class ProbeController {
        @GetMapping("/api/dashboard/indices")
        String indices() {
            return "ok";
        }
    }
}
