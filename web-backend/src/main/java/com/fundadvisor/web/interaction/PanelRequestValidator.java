package com.fundadvisor.web.interaction;

import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

final class PanelRequestValidator {

    private PanelRequestValidator() {}

    static String clientId(String value) {
        try {
            return UUID.fromString(value).toString();
        } catch (RuntimeException invalid) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "client_id must be a UUID",
                    invalid);
        }
    }

    static String fund(String value) {
        String normalized = value == null ? "" : value.trim();
        if (!normalized.matches("\\d{6}")) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "fund must be a 6 digit code");
        }
        return normalized;
    }
}
