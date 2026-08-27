package com.fundadvisor.web.agent;

import com.fundadvisor.web.config.BffProperties;
import java.net.URI;
import java.util.Locale;
import java.util.Set;
import org.springframework.core.io.buffer.DataBuffer;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.HttpStatusCode;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.client.WebClient;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import org.springframework.web.util.UriComponentsBuilder;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Component
public class AgentProxyHandler {

    private static final Set<String> HOP_BY_HOP_HEADERS = Set.of(
            "connection",
            "keep-alive",
            "proxy-authenticate",
            "proxy-authorization",
            "te",
            "trailer",
            "transfer-encoding",
            "upgrade",
            "host",
            "content-length");

    private final String agentApiUrl;
    private final WebClient webClient;

    public AgentProxyHandler(BffProperties properties, WebClient.Builder builder) {
        this.agentApiUrl = properties.agentApiUrl();
        this.webClient = builder.build();
    }

    public Mono<ServerResponse> proxy(ServerRequest request) {
        WebClient.RequestBodySpec upstream = webClient
                .method(request.method())
                .uri(upstreamUri(request));
        request.headers().asHttpHeaders().forEach((name, values) -> {
            if (!isHopByHop(name)) {
                upstream.header(name, values.toArray(String[]::new));
            }
        });

        Mono<ServerResponse> responseMono;
        if (hasRequestBody(request.method())) {
            responseMono = request.bodyToMono(byte[].class)
                    .defaultIfEmpty(new byte[0])
                    .flatMap(body -> body.length == 0
                            ? exchange(upstream)
                            : exchange(upstream.bodyValue(body)));
        } else {
            responseMono = exchange(upstream);
        }

        return responseMono;
    }

    private Mono<ServerResponse> exchange(WebClient.RequestHeadersSpec<?> upstream) {
        return upstream
                .retrieve()
                .onStatus(HttpStatusCode::isError, response -> Mono.empty())
                .toEntityFlux(DataBuffer.class)
                .flatMap(this::toServerResponse);
    }

    private Mono<ServerResponse> toServerResponse(ResponseEntity<Flux<DataBuffer>> response) {
        ServerResponse.BodyBuilder builder = ServerResponse.status(response.getStatusCode());
        response.getHeaders().forEach((name, values) -> {
            if (!isHopByHop(name)) {
                builder.header(name, values.toArray(String[]::new));
            }
        });
        MediaType contentType = response.getHeaders().getContentType();
        if (contentType != null && MediaType.TEXT_EVENT_STREAM.includes(contentType)) {
            // 覆盖式设置：上游若已带同名头，追加会产生 "no, no" 这类重复值，导致禁用缓冲失效。
            builder.headers(headers -> {
                headers.set("X-Accel-Buffering", "no");
                headers.set(HttpHeaders.CACHE_CONTROL, "no-cache");
            });
        }
        Flux<DataBuffer> body = response.getBody() == null ? Flux.empty() : response.getBody();
        return builder.body(BodyInserters.fromDataBuffers(body));
    }

    private URI upstreamUri(ServerRequest request) {
        return UriComponentsBuilder.fromUriString(agentApiUrl)
                .replacePath(request.uri().getRawPath())
                .replaceQuery(request.uri().getRawQuery())
                .build(true)
                .toUri();
    }

    private static boolean hasRequestBody(HttpMethod method) {
        return method == HttpMethod.POST
                || method == HttpMethod.PUT
                || method == HttpMethod.PATCH;
    }

    private static boolean isHopByHop(String headerName) {
        return HOP_BY_HOP_HEADERS.contains(headerName.toLowerCase(Locale.ROOT));
    }
}
