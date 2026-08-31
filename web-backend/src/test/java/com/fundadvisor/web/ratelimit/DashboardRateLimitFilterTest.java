package com.fundadvisor.web.ratelimit;

import static org.assertj.core.api.Assertions.assertThat;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.time.ZoneOffset;
import org.junit.jupiter.api.Test;
import org.springframework.mock.web.MockFilterChain;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.mock.web.MockHttpServletResponse;

class DashboardRateLimitFilterTest {

    private static final Clock CLOCK =
            Clock.fixed(Instant.parse("2026-08-27T10:00:00Z"), ZoneOffset.UTC);

    @Test
    void rejectsRequestsAboveTheConfiguredLimit() throws Exception {
        DashboardRateLimitFilter filter = new DashboardRateLimitFilter(
                (key, window) -> 3,
                new RateLimitProperties(true, 2, Duration.ofSeconds(60)),
                CLOCK);
        MockHttpServletRequest request = request("/api/dashboard/overview");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getStatus()).isEqualTo(429);
        assertThat(response.getHeader("Retry-After")).isEqualTo("60");
        assertThat(response.getContentAsString()).contains("rate limit exceeded");
    }

    @Test
    void failsOpenWhenRedisIsUnavailable() throws Exception {
        DashboardRateLimitFilter filter = new DashboardRateLimitFilter(
                (key, window) -> {
                    throw new IllegalStateException("redis down");
                },
                new RateLimitProperties(true, 2, Duration.ofSeconds(60)),
                CLOCK);
        MockHttpServletRequest request = request("/api/watchlist");
        MockHttpServletResponse response = new MockHttpServletResponse();

        filter.doFilter(request, response, new MockFilterChain());

        assertThat(response.getStatus()).isEqualTo(200);
    }

    @Test
    void doesNotRateLimitHealthOrAgentRoutes() throws Exception {
        DashboardRateLimitFilter filter = new DashboardRateLimitFilter(
                (key, window) -> 999,
                new RateLimitProperties(true, 1, Duration.ofSeconds(60)),
                CLOCK);
        for (String path : new String[] {"/health", "/api/chat/stream"}) {
            MockHttpServletResponse response = new MockHttpServletResponse();
            filter.doFilter(request(path), response, new MockFilterChain());
            assertThat(response.getStatus()).isEqualTo(200);
        }
    }

    private static MockHttpServletRequest request(String path) {
        MockHttpServletRequest request = new MockHttpServletRequest("GET", path);
        request.setRemoteAddr("127.0.0.1");
        return request;
    }
}
