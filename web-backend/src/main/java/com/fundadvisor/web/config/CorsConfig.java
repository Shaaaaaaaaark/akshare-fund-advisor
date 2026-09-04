package com.fundadvisor.web.config;

import java.util.Arrays;
import java.util.List;
import org.springframework.boot.web.servlet.FilterRegistrationBean;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.core.Ordered;
import org.springframework.web.cors.CorsConfiguration;
import org.springframework.web.cors.UrlBasedCorsConfigurationSource;
import org.springframework.web.filter.CorsFilter;

/**
 * 跨域过滤器。仅当配置了允许来源时才注册，且以最高优先级运行，
 * 保证在限流过滤器之前应答 CORS 预检（含流式 Agent 代理 /api/chat/**）。
 */
@Configuration
public class CorsConfig {

    @Bean
    FilterRegistrationBean<CorsFilter> corsFilterRegistration() {
        return corsFilterRegistration(System.getenv("WEB_CORS_ALLOWED_ORIGINS"));
    }

    static FilterRegistrationBean<CorsFilter> corsFilterRegistration(String rawOrigins) {
        UrlBasedCorsConfigurationSource source = new UrlBasedCorsConfigurationSource();
        List<String> origins = allowedOrigins(rawOrigins);
        if (!origins.isEmpty()) {
            CorsConfiguration config = new CorsConfiguration();
            config.setAllowedOrigins(origins);
            config.setAllowedMethods(List.of("GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"));
            config.setAllowedHeaders(List.of("*"));
            // 不使用 Cookie，保持 allowCredentials=false，允许精确来源即可。
            config.setMaxAge(1800L);
            source.registerCorsConfiguration("/api/**", config);
            source.registerCorsConfiguration("/health", config);
        }
        FilterRegistrationBean<CorsFilter> registration =
                new FilterRegistrationBean<>(new CorsFilter(source));
        // 早于限流过滤器（HIGHEST_PRECEDENCE + 20），确保预检不被限流拦截。
        registration.setOrder(Ordered.HIGHEST_PRECEDENCE);
        return registration;
    }

    static List<String> allowedOrigins(String rawOrigins) {
        if (rawOrigins == null || rawOrigins.isBlank()) {
            return List.of();
        }
        return Arrays.stream(rawOrigins.split(","))
                .map(String::trim)
                .map(CorsConfig::stripTrailingSlash)
                .filter(origin -> !origin.isEmpty())
                .distinct()
                .toList();
    }

    private static String stripTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
