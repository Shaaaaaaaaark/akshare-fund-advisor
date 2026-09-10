package com.fundadvisor.web.interaction;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import java.time.Clock;
import java.time.Instant;
import java.time.ZoneOffset;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;

class PanelCommentServiceTest {

    private static final String CLIENT_ID = "40c17919-6643-4a29-85db-a3f5e8b41d70";
    private static final Instant NOW = Instant.parse("2026-09-10T03:00:00Z");

    private PanelCommentMapper mapper;
    private PanelCommentService service;

    @BeforeEach
    void setUp() {
        mapper = org.mockito.Mockito.mock(PanelCommentMapper.class);
        service = new PanelCommentService(
                mapper,
                Clock.fixed(NOW, ZoneOffset.UTC));
    }

    @Test
    void createsNormalizedAnonymousComment() {
        PanelCommentView result = service.create(
                new CreatePanelCommentRequest(
                        CLIENT_ID,
                        "510310",
                        "  这个指标很好用\n希望增加历史对比  "));

        assertThat(result.content()).isEqualTo("这个指标很好用 希望增加历史对比");
        assertThat(result.visitorLabel()).startsWith("访客-");
        assertThat(result.mine()).isTrue();
        assertThat(result.createdAt()).isEqualTo(NOW);
        verify(mapper).insert(
                any(),
                eq("ETF:510310"),
                eq(CLIENT_ID),
                eq("这个指标很好用 希望增加历史对比"),
                eq(NOW));
    }

    @Test
    void listsPublishedCommentsWithoutExposingClientId() {
        when(mapper.findRecent("ETF:510310", 20))
                .thenReturn(List.of(
                        new PanelCommentRecord(
                                "comment-1",
                                "第一条评论",
                                CLIENT_ID,
                                NOW),
                        new PanelCommentRecord(
                                "comment-2",
                                "另一位访客",
                                "9405cc07-38c0-4acd-b825-856925d8c984",
                                NOW.minusSeconds(10))));
        when(mapper.countPublished("ETF:510310")).thenReturn(2);

        PanelCommentFeed result = service.list(CLIENT_ID, "510310", 20);

        assertThat(result.count()).isEqualTo(2);
        assertThat(result.comments()).extracting(PanelCommentView::mine)
                .containsExactly(true, false);
    }

    @Test
    void rejectsFrequentAndDuplicateComments() {
        CreatePanelCommentRequest request =
                new CreatePanelCommentRequest(CLIENT_ID, "510310", "重复评论");
        when(mapper.countRecentByClient(eq(CLIENT_ID), any()))
                .thenReturn(PanelCommentService.MAX_COMMENTS_PER_WINDOW);

        assertThatThrownBy(() -> service.create(request))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("comment rate limit exceeded");
        verify(mapper, never()).insert(any(), any(), any(), any(), any());

        when(mapper.countRecentByClient(eq(CLIENT_ID), any())).thenReturn(0);
        when(mapper.countRecentDuplicate(
                        eq("ETF:510310"),
                        eq(CLIENT_ID),
                        eq("重复评论"),
                        any()))
                .thenReturn(1);

        assertThatThrownBy(() -> service.create(request))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("duplicate comment");
        verify(mapper, never()).insert(any(), any(), any(), any(), any());
    }

    @Test
    void rejectsInvalidPageLimit() {
        assertThatThrownBy(() -> service.list(CLIENT_ID, "510310", 51))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("limit must be between 1 and 50");
    }
}
