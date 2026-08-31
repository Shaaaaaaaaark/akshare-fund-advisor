package com.fundadvisor.web.agent;

import java.io.IOException;
import java.io.InputStream;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.Enumeration;
import java.util.Locale;
import java.util.Set;

import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.web.servlet.mvc.method.annotation.StreamingResponseBody;

import com.fundadvisor.web.config.BffProperties;

import jakarta.servlet.http.HttpServletRequest;

@Controller
public class AgentProxyHandler {

    private static final int MAX_REQUEST_BYTES = 1024 * 1024;
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
    private final HttpClient httpClient;

    public AgentProxyHandler(BffProperties properties) {
        this.agentApiUrl = stripTrailingSlash(properties.agentApiUrl());
        this.httpClient = HttpClient.newBuilder()
                .connectTimeout(Duration.ofSeconds(10))
                .build();
    }

    @RequestMapping({ "/api/chat/**", "/api/sessions", "/api/sessions/**" })
    public ResponseEntity<StreamingResponseBody> proxy(HttpServletRequest request) {
        long contentLength = request.getContentLengthLong();
        if (contentLength > MAX_REQUEST_BYTES) {
            return ResponseEntity.status(413).build();
        }

        try {
            byte[] requestBody = hasRequestBody(request.getMethod())
                    ? request.getInputStream().readAllBytes()
                    : new byte[0];
            if (requestBody.length > MAX_REQUEST_BYTES) {
                return ResponseEntity.status(413).build();
            }

            HttpRequest.Builder upstream = HttpRequest.newBuilder(upstreamUri(request))
                    .method(
                            request.getMethod(),
                            requestBody.length == 0
                                    ? HttpRequest.BodyPublishers.noBody()
                                    : HttpRequest.BodyPublishers.ofByteArray(requestBody));
            copyRequestHeaders(request, upstream);

            HttpResponse<InputStream> response = httpClient.send(
                    upstream.build(),
                    HttpResponse.BodyHandlers.ofInputStream());
            HttpHeaders headers = copyResponseHeaders(response);
            StreamingResponseBody body = output -> {
                try (InputStream input = response.body()) {
                    byte[] buffer = new byte[8192];
                    int read;
                    while ((read = input.read(buffer)) >= 0) {
                        output.write(buffer, 0, read);
                        output.flush();
                    }
                }
            };

            return ResponseEntity.status(response.statusCode())
                    .headers(headers)
                    .body(body);
        } catch (InterruptedException exc) {
            Thread.currentThread().interrupt();
            throw new ResponseStatusException(
                    org.springframework.http.HttpStatus.BAD_GATEWAY,
                    "agent request interrupted",
                    exc);
        } catch (IOException | IllegalArgumentException exc) {
            throw new ResponseStatusException(
                    org.springframework.http.HttpStatus.BAD_GATEWAY,
                    "agent api unavailable",
                    exc);
        }
    }

    private void copyRequestHeaders(HttpServletRequest request, HttpRequest.Builder upstream) {
        Enumeration<String> names = request.getHeaderNames();
        while (names != null && names.hasMoreElements()) {
            String name = names.nextElement();
            if (!isHopByHop(name)) {
                Enumeration<String> values = request.getHeaders(name);
                while (values.hasMoreElements()) {
                    upstream.header(name, values.nextElement());
                }
            }
        }
    }

    private HttpHeaders copyResponseHeaders(HttpResponse<InputStream> response) {
        HttpHeaders headers = new HttpHeaders();
        response.headers().map().forEach((name, values) -> {
            if (!isHopByHop(name)) {
                headers.put(name, values);
            }
        });
        MediaType contentType = headers.getContentType();
        if (contentType != null && MediaType.TEXT_EVENT_STREAM.includes(contentType)) {
            headers.set("X-Accel-Buffering", "no");
            headers.setCacheControl("no-cache");
        }
        return headers;
    }

    private URI upstreamUri(HttpServletRequest request) {
        String query = request.getQueryString();
        return URI.create(agentApiUrl + request.getRequestURI() + (query == null ? "" : "?" + query));
    }

    private static boolean hasRequestBody(String method) {
        return "POST".equals(method) || "PUT".equals(method) || "PATCH".equals(method);
    }

    private static boolean isHopByHop(String headerName) {
        return HOP_BY_HOP_HEADERS.contains(headerName.toLowerCase(Locale.ROOT));
    }

    private static String stripTrailingSlash(String value) {
        return value.endsWith("/") ? value.substring(0, value.length() - 1) : value;
    }
}
