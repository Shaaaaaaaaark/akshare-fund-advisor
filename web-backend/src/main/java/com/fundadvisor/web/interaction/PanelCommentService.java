package com.fundadvisor.web.interaction;

import java.time.Clock;
import java.time.Duration;
import java.time.Instant;
import java.util.UUID;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PanelCommentService {

    static final int DEFAULT_LIMIT = 20;
    static final int MAX_LIMIT = 50;
    static final int MAX_COMMENTS_PER_WINDOW = 3;
    static final Duration RATE_WINDOW = Duration.ofMinutes(5);
    static final Duration DUPLICATE_WINDOW = Duration.ofMinutes(10);

    private final PanelCommentMapper mapper;
    private final Clock clock;

    public PanelCommentService(PanelCommentMapper mapper, Clock clock) {
        this.mapper = mapper;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public PanelCommentFeed list(String clientId, String fund, int limit) {
        String normalizedClientId = PanelRequestValidator.clientId(clientId);
        String normalizedFund = PanelRequestValidator.fund(fund);
        if (limit < 1 || limit > MAX_LIMIT) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "limit must be between 1 and 50");
        }
        String scope = scope(normalizedFund);
        var comments = mapper.findRecent(scope, limit).stream()
                .map(record -> view(record, normalizedClientId))
                .toList();
        return new PanelCommentFeed(
                normalizedFund,
                mapper.countPublished(scope),
                comments);
    }

    @Transactional
    public PanelCommentView create(CreatePanelCommentRequest request) {
        String clientId = PanelRequestValidator.clientId(request.clientId());
        String fund = PanelRequestValidator.fund(request.fund());
        String content = normalizeContent(request.content());
        String scope = scope(fund);
        Instant now = Instant.now(clock);

        if (mapper.countRecentByClient(clientId, now.minus(RATE_WINDOW))
                >= MAX_COMMENTS_PER_WINDOW) {
            throw new ResponseStatusException(
                    HttpStatus.TOO_MANY_REQUESTS,
                    "comment rate limit exceeded");
        }
        if (mapper.countRecentDuplicate(
                        scope,
                        clientId,
                        content,
                        now.minus(DUPLICATE_WINDOW))
                > 0) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "duplicate comment");
        }

        PanelCommentRecord record = new PanelCommentRecord(
                UUID.randomUUID().toString(),
                content,
                clientId,
                now);
        mapper.insert(
                record.id(),
                scope,
                record.clientId(),
                record.content(),
                record.createdAt());
        return view(record, clientId);
    }

    private static String normalizeContent(String value) {
        String raw = value == null ? "" : value.strip();
        if (raw.codePoints().anyMatch(
                codePoint ->
                        Character.isISOControl(codePoint)
                                && !Character.isWhitespace(codePoint))) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "content contains unsupported control characters");
        }
        String normalized = raw.replaceAll("[\\p{Z}\\s]+", " ");
        if (normalized.length() < 2 || normalized.length() > 280) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "content length must be between 2 and 280");
        }
        return normalized;
    }

    private static String scope(String fund) {
        return "ETF:" + fund;
    }

    private static PanelCommentView view(
            PanelCommentRecord record,
            String currentClientId) {
        return new PanelCommentView(
                record.id(),
                record.content(),
                visitorLabel(record.clientId()),
                record.clientId().equals(currentClientId),
                record.createdAt());
    }

    private static String visitorLabel(String clientId) {
        String token = Integer.toUnsignedString(clientId.hashCode(), 36)
                .toUpperCase();
        return "访客-" + token.substring(0, Math.min(4, token.length()));
    }
}
