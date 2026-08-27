package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fundadvisor.web.config.BffProperties;
import com.fundadvisor.web.dataapi.DashboardToolCaller;
import com.fundadvisor.web.facts.ToolEnvelope;
import java.time.OffsetDateTime;
import java.time.ZoneOffset;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import org.springframework.stereotype.Service;
import reactor.core.publisher.Flux;
import reactor.core.publisher.Mono;

@Service
public class DashboardService {

    static final String INDEX_VALUATION_TOOL = "index_valuation";
    static final String FUND_SEARCH_TOOL = "fund_search";
    static final String ETF_DASHBOARD_TOOL = "etf_dashboard";
    static final String FUND_ANALYZE_TOOL = "fund_analyze";
    static final String FUND_PROFILE_TOOL = "fund_profile";
    static final String FUND_RATING_TOOL = "fund_rating";
    static final String FUND_STATUS_TOOL = "fund_status";
    static final String STOCK_VALUATION_TOOL = "stock_valuation";

    private final DashboardToolCaller caller;
    private final ObjectMapper mapper;
    private final BffProperties properties;

    public DashboardService(DashboardToolCaller caller, ObjectMapper mapper, BffProperties properties) {
        this.caller = caller;
        this.mapper = mapper;
        this.properties = properties;
    }

    public Mono<IndicesResponse> indices() {
        return Flux.fromIterable(properties.indexUniverse())
                .flatMapSequential(this::indexRow, properties.concurrency())
                .collectList()
                .map(rows -> {
                    List<DataStatus> statuses = rows.stream().map(row -> row.meta().status()).toList();
                    rows.sort(Comparator.comparingInt(row -> statusRank(row.meta().status())));
                    return new IndicesResponse(rollUp(statuses), rows);
                });
    }

    public Mono<IndexDetail> indexDetail(String index, int years, int maxPoints) {
        int resolvedYears = years == 0 ? properties.indexYears() : years;
        Map<String, Object> arguments = maxPoints > 0
                ? Map.of("index", index, "years", resolvedYears, "max_points", maxPoints)
                : Map.of("index", index, "years", resolvedYears);
        return caller.callTool(INDEX_VALUATION_TOOL, arguments)
                .map(envelope -> {
                    String asOf = envelope.ok() ? indexAsOf(envelope.data()) : "";
                    return new IndexDetail(
                            index,
                            envelopeMeta(envelope, INDEX_VALUATION_TOOL, asOf),
                            envelope.rawJson());
                })
                .onErrorReturn(new IndexDetail(index, transportFailureMeta(INDEX_VALUATION_TOOL), null));
    }

    public Mono<FundSearchResponse> fundSearch(String query, int limit) {
        return caller.callTool(FUND_SEARCH_TOOL, Map.of("query", query, "limit", limit))
                .map(envelope -> new FundSearchResponse(
                        query,
                        envelopeMeta(envelope, FUND_SEARCH_TOOL, ""),
                        envelope.rawJson()))
                .onErrorReturn(new FundSearchResponse(query, transportFailureMeta(FUND_SEARCH_TOOL), null));
    }

    public Mono<ETFDetail> etfDetail(String fund, int years, int maxPoints) {
        return caller.callTool(
                        ETF_DASHBOARD_TOOL,
                        Map.of("fund", fund, "years", years, "max_points", maxPoints))
                .map(envelope -> {
                    String asOf = envelope.ok() ? textAt(envelope.data(), "summary", "latest_date") : "";
                    return new ETFDetail(
                            fund,
                            envelopeMeta(envelope, ETF_DASHBOARD_TOOL, asOf),
                            envelope.rawJson());
                })
                .onErrorReturn(new ETFDetail(fund, transportFailureMeta(ETF_DASHBOARD_TOOL), null));
    }

    public Mono<FundOverview> fundOverview(String fund, int years) {
        return caller.callTool(FUND_ANALYZE_TOOL, Map.of("fund", fund, "years", years))
                .map(envelope -> new FundOverview(
                        fund,
                        envelopeMeta(envelope, FUND_ANALYZE_TOOL, fundProductAsOf(FUND_ANALYZE_TOOL, envelope.data())),
                        envelope.rawJson()))
                .onErrorReturn(new FundOverview(fund, transportFailureMeta(FUND_ANALYZE_TOOL), null));
    }

    public Mono<FundProductResponse> fundProduct(String fund, int years) {
        Mono<FundProductSection> analysis = fundProductSection(
                FUND_ANALYZE_TOOL,
                Map.of("fund", fund, "years", years));
        Mono<FundProductSection> profile = fundProductSection(
                FUND_PROFILE_TOOL,
                Map.of("fund", fund));
        Mono<FundProductSection> rating = fundProductSection(
                FUND_RATING_TOOL,
                Map.of("fund", fund));
        Mono<FundProductSection> tradingStatus = fundProductSection(
                FUND_STATUS_TOOL,
                Map.of("fund", fund));

        return Mono.zip(analysis, profile, rating, tradingStatus)
                .map(tuple -> {
                    FundProductSections sections = new FundProductSections(
                            tuple.getT1(),
                            tuple.getT2(),
                            tuple.getT3(),
                            tuple.getT4());
                    DataStatus status = rollUp(List.of(
                            sections.analysis().meta().status(),
                            sections.profile().meta().status(),
                            sections.rating().meta().status(),
                            sections.tradingStatus().meta().status()));
                    return new FundProductResponse(fund, status, sections);
                });
    }

    public Mono<StockDetail> stockDetail(String stock, int years, int maxPoints) {
        return caller.callTool(
                        STOCK_VALUATION_TOOL,
                        Map.of("stock", stock, "years", years, "max_points", maxPoints))
                .map(envelope -> new StockDetail(
                        stock,
                        envelopeMeta(envelope, STOCK_VALUATION_TOOL, stockAsOf(envelope.data())),
                        envelope.rawJson()))
                .onErrorReturn(new StockDetail(stock, transportFailureMeta(STOCK_VALUATION_TOOL), null));
    }

    public Mono<OverviewResponse> overview() {
        BffProperties.OverviewTargets targets = properties.overview();
        return Mono.zip(
                        indexDetail(targets.index(), 10, 300),
                        etfDetail(targets.etf(), 3, 300),
                        fundOverview(targets.fund(), 3),
                        stockDetail(targets.stock(), 5, 300))
                .map(tuple -> {
                    OverviewCapability notImplemented = new OverviewCapability(
                            DataStatus.NOT_IMPLEMENTED,
                            "候选筛选工具尚未实现");
                    DataStatus status = rollUp(List.of(
                            tuple.getT1().meta().status(),
                            tuple.getT2().meta().status(),
                            tuple.getT3().meta().status(),
                            tuple.getT4().meta().status()));
                    return new OverviewResponse(
                            status,
                            tuple.getT1(),
                            tuple.getT2(),
                            tuple.getT3(),
                            tuple.getT4(),
                            notImplemented,
                            notImplemented);
                });
    }

    private Mono<IndexRow> indexRow(String index) {
        return caller.callTool(INDEX_VALUATION_TOOL, Map.of("index", index, "years", properties.indexYears()))
                .map(envelope -> {
                    DatasetMeta meta = envelopeMeta(envelope, INDEX_VALUATION_TOOL, "");
                    JsonNode peTtm = null;
                    JsonNode pb = null;
                    JsonNode latestPoint = null;
                    String asOf = "";
                    if (envelope.ok()) {
                        JsonNode data = envelope.data();
                        peTtm = nodeAt(data, "summary", "pe_ttm");
                        pb = nodeAt(data, "summary", "pb");
                        latestPoint = nodeAt(data, "charts", "index_points", "current");
                        asOf = indexAsOf(data);
                        meta = new DatasetMeta(
                                asOf,
                                meta.queriedAt(),
                                meta.status(),
                                meta.sourceTools(),
                                meta.auditRefs(),
                                meta.warnings(),
                                meta.error());
                    }
                    return new IndexRow(index, meta, peTtm, pb, latestPoint);
                })
                .onErrorReturn(new IndexRow(
                        index,
                        transportFailureMeta(INDEX_VALUATION_TOOL),
                        null,
                        null,
                        null));
    }

    private Mono<FundProductSection> fundProductSection(String tool, Map<String, Object> arguments) {
        return caller.callTool(tool, arguments)
                .map(envelope -> new FundProductSection(
                        envelopeMeta(envelope, tool, fundProductAsOf(tool, envelope.data())),
                        envelope.rawJson()))
                .onErrorReturn(new FundProductSection(transportFailureMeta(tool), null));
    }

    private DatasetMeta envelopeMeta(ToolEnvelope envelope, String tool, String asOf) {
        return new DatasetMeta(
                valueOrEmpty(asOf),
                envelope.queriedAt(),
                mapStatus(envelope),
                List.of(tool),
                envelope.frameHashes(),
                envelope.warningsRaw(mapper),
                envelope.errorRaw(mapper));
    }

    private DatasetMeta transportFailureMeta(String tool) {
        return new DatasetMeta(
                "",
                OffsetDateTime.now(ZoneOffset.UTC).toString(),
                DataStatus.UNAVAILABLE,
                List.of(tool),
                List.of(),
                null,
                null);
    }

    static DataStatus mapStatus(ToolEnvelope envelope) {
        if (envelope == null) {
            return DataStatus.UNAVAILABLE;
        }
        if (envelope.ok()) {
            return DataStatus.AVAILABLE;
        }
        String errorCode = envelope.errorCode();
        if (isStaleCode(errorCode)) {
            return DataStatus.STALE;
        }
        return DataStatus.UNAVAILABLE;
    }

    static DataStatus rollUp(List<DataStatus> statuses) {
        if (statuses == null || statuses.isEmpty()) {
            return DataStatus.UNAVAILABLE;
        }
        int available = 0;
        int stale = 0;
        int failed = 0;
        for (DataStatus status : statuses) {
            if (status == DataStatus.AVAILABLE) {
                available++;
            } else if (status == DataStatus.STALE) {
                stale++;
            } else if (status == DataStatus.UNAVAILABLE || status == DataStatus.NOT_IMPLEMENTED) {
                failed++;
            }
        }
        if (failed == statuses.size()) {
            return DataStatus.UNAVAILABLE;
        }
        if (failed > 0) {
            return DataStatus.PARTIAL;
        }
        if (stale > 0) {
            return DataStatus.STALE;
        }
        if (available == statuses.size()) {
            return DataStatus.AVAILABLE;
        }
        return DataStatus.PARTIAL;
    }

    private static boolean isStaleCode(String code) {
        String upper = code == null ? "" : code.toUpperCase(Locale.ROOT);
        return upper.equals("STALE_DATA")
                || upper.equals("STALE_OR_INVALID_DATA")
                || upper.contains("STALE");
    }

    private static int statusRank(DataStatus status) {
        return switch (status) {
            case AVAILABLE -> 0;
            case PARTIAL -> 1;
            case STALE -> 2;
            default -> 3;
        };
    }

    private static String indexAsOf(JsonNode data) {
        for (String value : List.of(
                textAt(data, "charts", "pe_ttm", "latest_date"),
                textAt(data, "charts", "pb", "latest_date"),
                textAt(data, "lookback", "latest_date"))) {
            if (!value.isEmpty()) {
                return value;
            }
        }
        return "";
    }

    private static String stockAsOf(JsonNode data) {
        String lookback = textAt(data, "lookback", "latest_date");
        if (!lookback.isEmpty()) {
            return lookback;
        }
        return textAt(data, "data_quality", "latest_date");
    }

    private static String fundProductAsOf(String tool, JsonNode data) {
        if (FUND_ANALYZE_TOOL.equals(tool)) {
            String dataQuality = textAt(data, "analysis", "data_quality", "latest_date");
            if (!dataQuality.isEmpty()) {
                return dataQuality;
            }
            return textAt(data, "metrics", "latest_date");
        }
        if (FUND_STATUS_TOOL.equals(tool)) {
            return textAt(data, "availability", "source_report_date");
        }
        return "";
    }

    private static JsonNode nodeAt(JsonNode root, String... path) {
        JsonNode current = root;
        for (String segment : path) {
            if (current == null || current.isNull() || current.isMissingNode()) {
                return null;
            }
            current = current.get(segment);
        }
        if (current == null || current.isNull() || current.isMissingNode()) {
            return null;
        }
        return current;
    }

    private static String textAt(JsonNode root, String... path) {
        JsonNode node = nodeAt(root, path);
        return ToolEnvelope.text(node);
    }

    private static String valueOrEmpty(String value) {
        return value == null ? "" : value;
    }
}
