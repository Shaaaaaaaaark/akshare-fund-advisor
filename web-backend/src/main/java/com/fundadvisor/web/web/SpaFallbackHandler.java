package com.fundadvisor.web.web;

import com.fundadvisor.web.config.BffProperties;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.MediaType;
import org.springframework.http.MediaTypeFactory;
import org.springframework.stereotype.Component;
import org.springframework.web.reactive.function.BodyInserters;
import org.springframework.web.reactive.function.server.ServerRequest;
import org.springframework.web.reactive.function.server.ServerResponse;
import reactor.core.publisher.Mono;

@Component
public class SpaFallbackHandler {

    private final Path staticDir;
    private final Path indexFile;

    public SpaFallbackHandler(BffProperties properties) {
        this.staticDir = properties.staticDir().toAbsolutePath().normalize();
        this.indexFile = staticDir.resolve("index.html").normalize();
    }

    public Mono<ServerResponse> handle(ServerRequest request) {
        String path = request.path();
        Path candidate = staticDir.resolve(stripLeadingSlash(path)).normalize();
        if (candidate.startsWith(staticDir) && Files.isRegularFile(candidate)) {
            return serve(candidate);
        }
        if (hasFileExtension(path)) {
            return ServerResponse.notFound().build();
        }
        if (!Files.isRegularFile(indexFile)) {
            return ServerResponse.notFound().build();
        }
        return serve(indexFile);
    }

    private Mono<ServerResponse> serve(Path path) {
        Resource resource = new FileSystemResource(path);
        MediaType mediaType = MediaTypeFactory.getMediaType(resource)
                .orElse(MediaType.APPLICATION_OCTET_STREAM);
        return ServerResponse.ok()
                .contentType(mediaType)
                .body(BodyInserters.fromResource(resource));
    }

    private String stripLeadingSlash(String path) {
        String value = path;
        while (value.startsWith("/")) {
            value = value.substring(1);
        }
        return value;
    }

    private boolean hasFileExtension(String path) {
        int slash = path.lastIndexOf('/');
        String name = slash >= 0 ? path.substring(slash + 1) : path;
        return name.contains(".");
    }
}
