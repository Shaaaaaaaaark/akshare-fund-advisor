package com.fundadvisor.web.watchlist;

import java.time.Clock;
import java.time.Instant;
import java.util.List;
import java.util.Locale;
import java.util.UUID;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class WatchlistService {

    static final int MAX_ITEMS = 100;

    private final WatchlistMapper mapper;
    private final Clock clock;

    public WatchlistService(WatchlistMapper mapper, Clock clock) {
        this.mapper = mapper;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public List<WatchlistItem> findAll() {
        return mapper.findAll();
    }

    @Transactional
    public WatchlistItem create(CreateWatchlistItemRequest request) {
        if (mapper.count() >= MAX_ITEMS) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "watchlist supports at most " + MAX_ITEMS + " items");
        }

        WatchlistItem item = new WatchlistItem(
                UUID.randomUUID().toString(),
                request.entityType(),
                normalizeCode(request.entityCode()),
                request.displayName().trim(),
                Instant.now(clock));
        try {
            mapper.insert(
                    item.id(),
                    item.entityType(),
                    item.entityCode(),
                    item.displayName(),
                    item.createdAt());
        } catch (DuplicateKeyException exc) {
            throw new ResponseStatusException(
                    HttpStatus.CONFLICT,
                    "the entity is already in the watchlist",
                    exc);
        }
        return item;
    }

    @Transactional
    public void delete(String id) {
        if (id == null || id.isBlank() || mapper.deleteById(id) == 0) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "watchlist item not found");
        }
    }

    private static String normalizeCode(String code) {
        String normalized = code.trim().toUpperCase(Locale.ROOT);
        if (normalized.chars().anyMatch(Character::isISOControl)) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "entity_code contains control characters");
        }
        return normalized;
    }
}
