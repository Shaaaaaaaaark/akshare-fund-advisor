package com.fundadvisor.web.web;

import com.fundadvisor.web.agent.AgentProxyHandler;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.reactive.function.server.RequestPredicates;
import org.springframework.web.reactive.function.server.RouterFunction;
import org.springframework.web.reactive.function.server.RouterFunctions;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;

@Configuration
public class WebRoutes {

    @Bean
    RouterFunction<ServerResponse> routes(
            AgentProxyHandler agentProxy,
            SpaFallbackHandler spaFallback) {
        return RouterFunctions.route()
                .route(RequestPredicates.path("/api/chat/**"), agentProxy::proxy)
                .route(RequestPredicates.path("/api/sessions"), agentProxy::proxy)
                .route(RequestPredicates.path("/api/sessions/**"), agentProxy::proxy)
                .route(RequestPredicates.GET("/**").and(this::isSpaPath), spaFallback::handle)
                .build();
    }

    private boolean isSpaPath(ServerRequest request) {
        String path = request.path();
        return !path.equals("/health")
                && !path.startsWith("/api/")
                && !path.startsWith("/actuator/");
    }
}
