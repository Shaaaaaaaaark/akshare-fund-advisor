package com.fundadvisor.web.interaction;

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
import org.springframework.web.server.ResponseStatusException;

class PanelInteractionServiceTest {

    private static final String CLIENT_ID = "40c17919-6643-4a29-85db-a3f5e8b41d70";
    private static final String HOT_POLL_TOPIC = "sector_20260910_012345abcdef";

    private PanelInteractionMapper mapper;
    private PanelInteractionService service;

    @BeforeEach
    void setUp() {
        mapper = org.mockito.Mockito.mock(PanelInteractionMapper.class);
        service = new PanelInteractionService(
                mapper,
                Clock.fixed(Instant.parse("2026-08-28T03:00:00Z"), ZoneOffset.UTC));
    }

    @Test
    void createsAnIdempotentHotPollSelectionAndReturnsCounts() {
        when(mapper.updateChoice(
                        "hot_poll",
                        PanelInteractionService.GLOBAL_SCOPE,
                        HOT_POLL_TOPIC,
                        "yes",
                        CLIENT_ID,
                        Instant.parse("2026-08-28T03:00:00Z")))
                .thenReturn(0);
        when(mapper.countByOption(
                        "hot_poll",
                        PanelInteractionService.GLOBAL_SCOPE,
                        HOT_POLL_TOPIC))
                .thenReturn(List.of(new InteractionOptionCount("yes", 1L)));
        when(mapper.findSelection(
                        "hot_poll",
                        PanelInteractionService.GLOBAL_SCOPE,
                        HOT_POLL_TOPIC,
                        CLIENT_ID))
                .thenReturn("yes");

        PanelInteractionSummary summary = service.submit(
                new SubmitPanelInteractionRequest(
                        PanelInteractionKind.HOT_POLL,
                        HOT_POLL_TOPIC,
                        "yes",
                        CLIENT_ID,
                        "510310"));

        assertThat(summary.hotPolls().get(HOT_POLL_TOPIC).counts().get("yes"))
                .isEqualTo(1);
        assertThat(summary.hotPolls().get(HOT_POLL_TOPIC).selectedOption())
                .isEqualTo("yes");
        verify(mapper).insert(
                anyString(),
                org.mockito.ArgumentMatchers.eq("hot_poll"),
                org.mockito.ArgumentMatchers.eq(PanelInteractionService.GLOBAL_SCOPE),
                org.mockito.ArgumentMatchers.eq(HOT_POLL_TOPIC),
                org.mockito.ArgumentMatchers.eq("yes"),
                org.mockito.ArgumentMatchers.eq(CLIENT_ID),
                any(),
                any());
    }

    @Test
    void updatesExistingFeedbackInsteadOfCreatingAnotherVote() {
        when(mapper.updateChoice(
                        "feedback",
                        "ETF:510310",
                        PanelInteractionService.FEEDBACK_TOPIC,
                        "useful",
                        CLIENT_ID,
                        Instant.parse("2026-08-28T03:00:00Z")))
                .thenReturn(1);

        service.submit(
                new SubmitPanelInteractionRequest(
                        PanelInteractionKind.FEEDBACK,
                        PanelInteractionService.FEEDBACK_TOPIC,
                        "useful",
                        CLIENT_ID,
                        "510310"));

        verify(mapper, never()).insert(
                anyString(),
                anyString(),
                anyString(),
                anyString(),
                anyString(),
                anyString(),
                any(),
                any());
    }

    @Test
    void rejectsUnknownTopicsAndOptions() {
        assertThatThrownBy(() -> service.submit(
                        new SubmitPanelInteractionRequest(
                                PanelInteractionKind.HOT_POLL,
                                "unknown",
                                "yes",
                                CLIENT_ID,
                                "510310")))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("unsupported hot poll topic");

        assertThatThrownBy(() -> service.submit(
                        new SubmitPanelInteractionRequest(
                                PanelInteractionKind.FEATURE_VOTE,
                                PanelInteractionService.FEATURE_TOPIC,
                                "arbitrary",
                                CLIENT_ID,
                                "510310")))
                .isInstanceOf(ResponseStatusException.class)
                .hasMessageContaining("unsupported interaction option");
    }
}
