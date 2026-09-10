package com.fundadvisor.web.interaction;

import jakarta.validation.Valid;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/panel/comments")
public class PanelCommentController {

    private final PanelCommentService service;

    public PanelCommentController(PanelCommentService service) {
        this.service = service;
    }

    @GetMapping
    public PanelCommentFeed list(
            @RequestParam("client_id") String clientId,
            @RequestParam String fund,
            @RequestParam(defaultValue = "20") int limit) {
        return service.list(clientId, fund, limit);
    }

    @PostMapping
    public ResponseEntity<PanelCommentView> create(
            @Valid @RequestBody CreatePanelCommentRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED)
                .body(service.create(request));
    }
}
