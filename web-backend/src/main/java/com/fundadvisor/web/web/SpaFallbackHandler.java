package com.fundadvisor.web.web;

import com.fundadvisor.web.config.BffProperties;
import java.nio.file.Files;
import java.nio.file.Path;
import org.springframework.core.io.FileSystemResource;
import org.springframework.core.io.Resource;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.stereotype.Controller;
import org.springframework.web.bind.annotation.GetMapping;

@Controller
public class SpaFallbackHandler {

    private final Path indexFile;

    public SpaFallbackHandler(BffProperties properties) {
        this.indexFile = properties.staticDir().toAbsolutePath().normalize().resolve("index.html");
    }

    @GetMapping(
            value = {
                "/",
                "/overview",
                "/indices",
                "/indices/{index}",
                "/funds",
                "/funds/{fund}",
                "/funds/{fund}/product",
                "/stocks",
                "/stocks/{stock}",
                "/watchlist",
                "/chat"
            },
            produces = MediaType.TEXT_HTML_VALUE)
    public ResponseEntity<Resource> index() {
        if (!Files.isRegularFile(indexFile)) {
            return ResponseEntity.status(HttpStatus.NOT_FOUND).build();
        }
        return ResponseEntity.ok()
                .contentType(MediaType.TEXT_HTML)
                .body(new FileSystemResource(indexFile));
    }
}
