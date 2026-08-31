package com.fundadvisor.web.ratelimit;

import jakarta.servlet.FilterChain;
import jakarta.servlet.ServletException;
import jakarta.servlet.http.HttpServletRequest;
import jakarta.servlet.http.HttpServletResponse;
import java.io.IOException;
import java.time.Clock;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.core.Ordered;
import org.springframework.core.annotation.Order;
import org.springframework.http.MediaType;
import org.springframework.stereotype.Component;
import org.springframework.web.filter.OncePerRequestFilter;

@Component
@Order(Ordered.HIGHEST_PRECEDENCE + 20)
public class DashboardRateLimitFilter extends OncePerRequestFilter {

    private static final Logger log = LoggerFactory.getLogger(DashboardRateLimitFilter.class);

    private final RateLimitStore store;
    private final RateLimitProperties properties;
    private final Clock clock;

    public DashboardRateLimitFilter(
            RateLimitStore store,
            RateLimitProperties properties,
            Clock clock) {
        this.store = store;
        this.properties = properties;
        this.clock = clock;
    }

    @Override
    protected boolean shouldNotFilter(HttpServletRequest request) {
        String path = request.getRequestURI();
        return !properties.enabled()
                || (!path.startsWith("/api/dashboard/")
                        && !path.startsWith("/api/watchlist")
                        && !path.startsWith("/api/panel/"));
    }

    @Override
    protected void doFilterInternal(
            HttpServletRequest request,
            HttpServletResponse response,
            FilterChain filterChain)
            throws ServletException, IOException {
        long windowSeconds = properties.window().toSeconds();
        long window = clock.instant().getEpochSecond() / windowSeconds;
        String key = "rate:dashboard:" + request.getRemoteAddr() + ":" + window;

        try {
            long requests = store.increment(key, properties.window());
            if (requests > properties.requests()) {
                response.setStatus(429);
                response.setContentType(MediaType.APPLICATION_JSON_VALUE);
                response.setCharacterEncoding("UTF-8");
                response.setHeader("Retry-After", Long.toString(windowSeconds));
                response.getWriter().write("{\"detail\":\"dashboard request rate limit exceeded\"}");
                return;
            }
        } catch (RuntimeException exc) {
            log.warn("redis rate limiter unavailable; allowing request: {}", exc.getMessage());
            log.debug("redis rate limiter failure details", exc);
        }

        filterChain.doFilter(request, response);
    }
}
