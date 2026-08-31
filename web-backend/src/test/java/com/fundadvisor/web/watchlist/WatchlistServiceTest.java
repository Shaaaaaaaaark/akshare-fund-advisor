package com.fundadvisor.web.watchlist;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.web.server.ResponseStatusException;

class WatchlistServiceTest {

    private WatchlistMapper mapper;
    private WatchlistService service;

    @BeforeEach
    void setUp() {
        mapper = org.mockito.Mockito.mock(WatchlistMapper.class);
        service = new WatchlistService(
                mapper,
                Clock.fixed(Instant.parse("2026-08-27T10:00:00Z"), ZoneOffset.UTC));
    }

    @Test
    void createsNormalizedWatchlistItem() {
        when(mapper.insert(anyString(), any(), anyString(), anyString(), any())).thenReturn(1);

        WatchlistItem item = service.create(
                new CreateWatchlistItemRequest(EntityType.STOCK, " sh600519 ", " 贵州茅台 "));

        assertThat(item.entityCode()).isEqualTo("SH600519");
        assertThat(item.displayName()).isEqualTo("贵州茅台");
        assertThat(item.createdAt()).isEqualTo(Instant.parse("2026-08-27T10:00:00Z"));
        verify(mapper).insert(item.id(), EntityType.STOCK, "SH600519", "贵州茅台", item.createdAt());
    }

    @Test
    void rejectsDuplicateAndCapacityOverflow() {
        when(mapper.insert(anyString(), any(), anyString(), anyString(), any()))
                .thenThrow(new DuplicateKeyException("duplicate"));

        assertThatThrownBy(() -> service.create(
                        new CreateWatchlistItemRequest(EntityType.FUND, "000001", "华夏成长")))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("already in the watchlist");

        when(mapper.count()).thenReturn(WatchlistService.MAX_ITEMS);
        assertThatThrownBy(() -> service.create(
                        new CreateWatchlistItemRequest(EntityType.ETF, "510300", "沪深300ETF")))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("at most");
        verify(mapper, never()).insert(anyString(), any(), org.mockito.ArgumentMatchers.eq("510300"), anyString(), any());
    }

    @Test
    void listsAndDeletesItems() {
        WatchlistItem item =
                new WatchlistItem("id-1", EntityType.INDEX, "沪深300", "沪深300", Instant.EPOCH);
        when(mapper.findAll()).thenReturn(List.of(item));
        when(mapper.deleteById("id-1")).thenReturn(1);

        assertThat(service.findAll()).containsExactly(item);
        service.delete("id-1");

        verify(mapper).deleteById("id-1");
    }

    @Test
    void deletingUnknownItemReturnsNotFound() {
        when(mapper.deleteById("missing")).thenReturn(0);

        assertThatThrownBy(() -> service.delete("missing"))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("watchlist item not found");
    }
}
