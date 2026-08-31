package com.fundadvisor.web.interaction;

import jakarta.validation.Valid;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PostMapping;
import org.springframework.web.bind.annotation.RequestBody;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/panel/interactions")
public class PanelInteractionController {

    private final PanelInteractionService service;

    public PanelInteractionController(PanelInteractionService service) {
        this.service = service;
    }

    @GetMapping
    public PanelInteractionSummary summary(
            @RequestParam("client_id") String clientId,
            @RequestParam String fund) {
        return service.summary(clientId, fund);
    }

    @PostMapping
    public PanelInteractionSummary submit(
            @Valid @RequestBody SubmitPanelInteractionRequest request) {
        return service.submit(request);
    }
}
