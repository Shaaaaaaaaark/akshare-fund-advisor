package com.fundadvisor.web.interaction;

import java.time.Clock;
import java.time.Instant;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;
import java.util.UUID;
import java.util.regex.Pattern;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
public class PanelInteractionService {

    static final String GLOBAL_SCOPE = "GLOBAL";
    static final String FEEDBACK_TOPIC = "etf_feedback";
    static final String FEATURE_TOPIC = "next_feature";

    private static final Pattern HOT_POLL_TOPIC =
            Pattern.compile("^sector_\\d{8}_[0-9a-f]{12}$");
    private static final int MAX_HOT_POLL_TOPICS = 8;
    private static final Set<String> HOT_POLL_OPTIONS = Set.of("yes", "no");
    private static final Set<String> FEEDBACK_OPTIONS =
            Set.of("useful", "unclear", "data_question", "want_explanation");
    private static final Set<String> FEATURE_OPTIONS = Set.of(
            "index_futures",
            "insurance_etf_holdings",
            "deposit_account_flow",
            "fund_crowding",
            "other");

    private final PanelInteractionMapper mapper;
    private final Clock clock;

    public PanelInteractionService(PanelInteractionMapper mapper, Clock clock) {
        this.mapper = mapper;
        this.clock = clock;
    }

    @Transactional(readOnly = true)
    public PanelInteractionSummary summary(
            String clientId,
            String fund,
            List<String> hotPollTopics) {
        String normalizedClientId = PanelRequestValidator.clientId(clientId);
        String normalizedFund = PanelRequestValidator.fund(fund);
        Map<String, PanelTopicSummary> polls = new LinkedHashMap<>();
        for (String topic : validateHotPollTopics(hotPollTopics)) {
            polls.put(
                    topic,
                    topicSummary(
                            PanelInteractionKind.HOT_POLL,
                            GLOBAL_SCOPE,
                            topic,
                            HOT_POLL_OPTIONS,
                            normalizedClientId));
        }
        return new PanelInteractionSummary(
                normalizedFund,
                polls,
                topicSummary(
                        PanelInteractionKind.FEEDBACK,
                        feedbackScope(normalizedFund),
                        FEEDBACK_TOPIC,
                        FEEDBACK_OPTIONS,
                        normalizedClientId),
                topicSummary(
                        PanelInteractionKind.FEATURE_VOTE,
                        GLOBAL_SCOPE,
                        FEATURE_TOPIC,
                        FEATURE_OPTIONS,
                        normalizedClientId));
    }

    @Transactional
    public PanelInteractionSummary submit(SubmitPanelInteractionRequest request) {
        String clientId = PanelRequestValidator.clientId(request.clientId());
        String fund = PanelRequestValidator.fund(request.fund());
        String topic = request.topicKey().trim();
        String option = request.optionKey().trim();
        Set<String> allowedOptions = allowedOptions(request.kind(), topic);
        if (!allowedOptions.contains(option)) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "unsupported interaction option");
        }
        String scope = scopeFor(request.kind(), fund);
        Instant now = Instant.now(clock);
        if (mapper.updateChoice(
                        request.kind().value(),
                        scope,
                        topic,
                        option,
                        clientId,
                        now)
                == 0) {
            try {
                mapper.insert(
                        UUID.randomUUID().toString(),
                        request.kind().value(),
                        scope,
                        topic,
                        option,
                        clientId,
                        now,
                        now);
            } catch (DuplicateKeyException conflict) {
                if (mapper.updateChoice(
                                request.kind().value(),
                                scope,
                                topic,
                                option,
                                clientId,
                                now)
                        == 0) {
                    throw conflict;
                }
            }
        }
        List<String> hotPollTopics = request.kind() == PanelInteractionKind.HOT_POLL
                ? List.of(topic)
                : List.of();
        return summary(clientId, fund, hotPollTopics);
    }

    private PanelTopicSummary topicSummary(
            PanelInteractionKind kind,
            String scope,
            String topic,
            Set<String> allowedOptions,
            String clientId) {
        Map<String, Long> counts = new LinkedHashMap<>();
        allowedOptions.stream().sorted().forEach(option -> counts.put(option, 0L));
        for (InteractionOptionCount count :
                mapper.countByOption(kind.value(), scope, topic)) {
            if (counts.containsKey(count.optionKey())) {
                counts.put(count.optionKey(), count.count());
            }
        }
        String selected = mapper.findSelection(
                kind.value(),
                scope,
                topic,
                clientId);
        return new PanelTopicSummary(
                counts,
                selected != null && allowedOptions.contains(selected)
                        ? selected
                        : null);
    }

    private static Set<String> allowedOptions(
            PanelInteractionKind kind,
            String topic) {
        return switch (kind) {
            case HOT_POLL -> {
                if (!HOT_POLL_TOPIC.matcher(topic).matches()) {
                    throw new ResponseStatusException(
                            HttpStatus.BAD_REQUEST,
                            "unsupported hot poll topic");
                }
                yield HOT_POLL_OPTIONS;
            }
            case FEEDBACK -> {
                if (!FEEDBACK_TOPIC.equals(topic)) {
                    throw new ResponseStatusException(
                            HttpStatus.BAD_REQUEST,
                            "unsupported feedback topic");
                }
                yield FEEDBACK_OPTIONS;
            }
            case FEATURE_VOTE -> {
                if (!FEATURE_TOPIC.equals(topic)) {
                    throw new ResponseStatusException(
                            HttpStatus.BAD_REQUEST,
                            "unsupported feature vote topic");
                }
                yield FEATURE_OPTIONS;
            }
        };
    }

    private static String scopeFor(
            PanelInteractionKind kind,
            String fund) {
        return kind == PanelInteractionKind.FEEDBACK
                ? feedbackScope(fund)
                : GLOBAL_SCOPE;
    }

    private static String feedbackScope(String fund) {
        return "ETF:" + fund;
    }

    private static List<String> validateHotPollTopics(List<String> topics) {
        if (topics == null || topics.isEmpty()) {
            return List.of();
        }
        if (topics.size() > MAX_HOT_POLL_TOPICS) {
            throw new ResponseStatusException(
                    HttpStatus.BAD_REQUEST,
                    "at most 8 hot poll topics are supported");
        }
        Set<String> normalized = new LinkedHashSet<>();
        for (String topic : topics) {
            String value = topic == null ? "" : topic.trim();
            if (!HOT_POLL_TOPIC.matcher(value).matches()) {
                throw new ResponseStatusException(
                        HttpStatus.BAD_REQUEST,
                        "unsupported hot poll topic");
            }
            normalized.add(value);
        }
        return List.copyOf(normalized);
    }

}
