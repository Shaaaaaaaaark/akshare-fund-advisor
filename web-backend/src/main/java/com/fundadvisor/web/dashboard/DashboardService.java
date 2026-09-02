package com.fundadvisor.web.dashboard;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ObjectNode;
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
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.Executor;
import java.util.function.Supplier;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.stereotype.Service;

@Service
public class DashboardService {

    static final String UPSTREAM_ERROR_CODE = "UPSTREAM_ERROR";
    static final String INDEX_VALUATION_TOOL = "index_valuation";
    static final String FUND_SEARCH_TOOL = "fund_search";
    static final String ETF_DASHBOARD_TOOL = "etf_dashboard";
    static final String FUND_ANALYZE_TOOL = "fund_analyze";
    static final String FUND_PROFILE_TOOL = "fund_profile";
    static final String FUND_RATING_TOOL = "fund_rating";
    static final String FUND_STATUS_TOOL = "fund_status";
    static final String STOCK_VALUATION_TOOL = "stock_valuation";
    static final String QDII_PURCHASE_BOARD_TOOL = "qdii_purchase_board";

    private static final Logger log = LoggerFactory.getLogger(DashboardService.class);

    private final DashboardToolCaller caller;
    private final ObjectMapper mapper;
    private final BffProperties properties;
    private final Executor taskExecutor;

    public DashboardService(
            DashboardToolCaller caller,
            ObjectMapper mapper,
            BffProperties properties,
            Executor taskExecutor) {
        this.caller = caller;
        this.mapper = mapper;
        this.properties = properties;
        this.taskExecutor = taskExecutor;
    }

    public IndicesResponse indices() {
        List<IndexRow> rows = invokeAll(properties.indexUniverse().stream()
                .<Supplier<IndexRow>>map(index -> () -> indexRow(index))
                .toList());
        List<DataStatus> statuses = rows.stream().map(row -> row.meta().status()).toList();
        rows.sort(Comparator.comparingInt(row -> statusRank(row.meta().status())));
        return new IndicesResponse(rollUp(statuses), rows);
    }

    public IndexDetail indexDetail(String index, int years, int maxPoints) {
        int resolvedYears = years == 0 ? properties.indexYears() : years;
        Map<String, Object> arguments = maxPoints > 0
                ? Map.of("index", index, "years", resolvedYears, "max_points", maxPoints)
                : Map.of("index", index, "years", resolvedYears);
        try {
            ToolEnvelope envelope = caller.callTool(INDEX_VALUATION_TOOL, arguments);
            String asOf = envelope.ok() ? indexAsOf(envelope.data()) : "";
            return new IndexDetail(
                    index,
                    envelopeMeta(envelope, INDEX_VALUATION_TOOL, asOf),
                    envelope.rawJson());
        } catch (RuntimeException error) {
            return new IndexDetail(index, transportFailureMeta(INDEX_VALUATION_TOOL, error), null);
        }
    }

    public FundSearchResponse fundSearch(String query, int limit) {
        try {
            ToolEnvelope envelope = caller.callTool(FUND_SEARCH_TOOL, Map.of("query", query, "limit", limit));
            return new FundSearchResponse(
                    query,
                    envelopeMeta(envelope, FUND_SEARCH_TOOL, ""),
                    envelope.rawJson());
        } catch (RuntimeException error) {
            return new FundSearchResponse(query, transportFailureMeta(FUND_SEARCH_TOOL, error), null);
        }
    }

    public ETFDetail etfDetail(String fund, int years, int maxPoints) {
        try {
            ToolEnvelope envelope = caller.callTool(
                    ETF_DASHBOARD_TOOL,
                    Map.of("fund", fund, "years", years, "max_points", maxPoints));
            String asOf = envelope.ok() ? textAt(envelope.data(), "summary", "latest_date") : "";
            return new ETFDetail(
                    fund,
                    envelopeMeta(envelope, ETF_DASHBOARD_TOOL, asOf),
                    envelope.rawJson());
        } catch (RuntimeException error) {
            return new ETFDetail(fund, transportFailureMeta(ETF_DASHBOARD_TOOL, error), null);
        }
    }

    public FundOverview fundOverview(String fund, int years) {
        try {
            ToolEnvelope envelope = caller.callTool(FUND_ANALYZE_TOOL, Map.of("fund", fund, "years", years));
            return new FundOverview(
                    fund,
                    envelopeMeta(envelope, FUND_ANALYZE_TOOL, fundProductAsOf(FUND_ANALYZE_TOOL, envelope.data())),
                    envelope.rawJson());
        } catch (RuntimeException error) {
            return new FundOverview(fund, transportFailureMeta(FUND_ANALYZE_TOOL, error), null);
        }
    }

    public FundProductResponse fundProduct(String fund, int years) {
        List<FundProductSection> values = invokeAll(List.of(
                () -> fundProductSection(FUND_ANALYZE_TOOL, Map.of("fund", fund, "years", years)),
                () -> fundProductSection(FUND_PROFILE_TOOL, Map.of("fund", fund)),
                () -> fundProductSection(FUND_RATING_TOOL, Map.of("fund", fund)),
                () -> fundProductSection(FUND_STATUS_TOOL, Map.of("fund", fund))));
        FundProductSections sections = new FundProductSections(
                values.get(0),
                values.get(1),
                values.get(2),
                values.get(3));
        DataStatus status = rollUp(List.of(
                sections.analysis().meta().status(),
                sections.profile().meta().status(),
                sections.rating().meta().status(),
                sections.tradingStatus().meta().status()));
        return new FundProductResponse(fund, status, sections);
    }

    public StockDetail stockDetail(String stock, int years, int maxPoints) {
        try {
            ToolEnvelope envelope = caller.callTool(
                    STOCK_VALUATION_TOOL,
                    Map.of("stock", stock, "years", years, "max_points", maxPoints));
            return new StockDetail(
                    stock,
                    envelopeMeta(envelope, STOCK_VALUATION_TOOL, stockAsOf(envelope.data())),
                    envelope.rawJson());
        } catch (RuntimeException error) {
            return new StockDetail(stock, transportFailureMeta(STOCK_VALUATION_TOOL, error), null);
        }
    }

    public BoardDetail qdiiPurchaseBoard() {
        try {
            ToolEnvelope envelope = caller.callTool(QDII_PURCHASE_BOARD_TOOL, Map.of());
            return new BoardDetail(
                    "qdii-purchase",
                    envelopeMeta(envelope, QDII_PURCHASE_BOARD_TOOL, boardAsOf(envelope.data())),
                    envelope.rawJson());
        } catch (RuntimeException error) {
            return new BoardDetail("qdii-purchase", transportFailureMeta(QDII_PURCHASE_BOARD_TOOL, error), null);
        }
    }

    public OverviewResponse overview() {
        BffProperties.OverviewTargets targets = properties.overview();
        CompletableFuture<IndexDetail> indexFuture =
                submit(() -> indexDetail(targets.index(), 10, 300));
        CompletableFuture<ETFDetail> etfFuture =
                submit(() -> etfDetail(targets.etf(), 3, 300));
        CompletableFuture<FundOverview> fundFuture =
                submit(() -> fundOverview(targets.fund(), 3));
        CompletableFuture<StockDetail> stockFuture =
                submit(() -> stockDetail(targets.stock(), 5, 300));
        IndexDetail index = indexFuture.join();
        ETFDetail etf = etfFuture.join();
        FundOverview fund = fundFuture.join();
        StockDetail stock = stockFuture.join();
        OverviewCapability notImplemented = new OverviewCapability(
                DataStatus.NOT_IMPLEMENTED,
                "候选筛选工具尚未实现");
        DataStatus status = rollUp(List.of(
                index.meta().status(),
                etf.meta().status(),
                fund.meta().status(),
                stock.meta().status()));
        return new OverviewResponse(
                status,
                index,
                etf,
                fund,
                stock,
                notImplemented,
                notImplemented);
    }

    private IndexRow indexRow(String index) {
        try {
            ToolEnvelope envelope = caller.callTool(
                    INDEX_VALUATION_TOOL,
                    Map.of("index", index, "years", properties.indexYears()));
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
        } catch (RuntimeException error) {
            return new IndexRow(
                    index,
                    transportFailureMeta(INDEX_VALUATION_TOOL, error),
                    null,
                    null,
                    null);
        }
    }

    private FundProductSection fundProductSection(String tool, Map<String, Object> arguments) {
        try {
            ToolEnvelope envelope = caller.callTool(tool, arguments);
            return new FundProductSection(
                    envelopeMeta(envelope, tool, fundProductAsOf(tool, envelope.data())),
                    envelope.rawJson());
        } catch (RuntimeException error) {
            return new FundProductSection(transportFailureMeta(tool, error), null);
        }
    }

    private <T> List<T> invokeAll(List<Supplier<T>> tasks) {
        List<T> results = new ArrayList<>(tasks.size());
        for (int start = 0; start < tasks.size(); start += properties.concurrency()) {
            int end = Math.min(start + properties.concurrency(), tasks.size());
            List<CompletableFuture<T>> batch = tasks.subList(start, end).stream()
                    .map(task -> CompletableFuture.supplyAsync(task, taskExecutor))
                    .toList();
            batch.stream().map(CompletableFuture::join).forEach(results::add);
        }
        return results;
    }

    private <T> CompletableFuture<T> submit(Supplier<T> task) {
        return CompletableFuture.supplyAsync(task, taskExecutor);
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

    private DatasetMeta transportFailureMeta(String tool, Throwable error) {
        log.warn("data api {} transport failure: {}", tool, describe(error));
        log.debug("data api {} transport failure details", tool, error);
        return new DatasetMeta(
                "",
                OffsetDateTime.now(ZoneOffset.UTC).toString(),
                DataStatus.UNAVAILABLE,
                List.of(tool),
                List.of(),
                null,
                upstreamErrorRaw(tool, error));
    }

    /** 透传上游失败原因，只描述错误本身，不补任何金融数值。 */
    private String upstreamErrorRaw(String tool, Throwable error) {
        ObjectNode node = mapper.createObjectNode();
        node.put("code", UPSTREAM_ERROR_CODE);
        node.put("message", tool + " 取数失败：" + describe(error));
        node.put("retryable", true);
        return node.toString();
    }

    private static String describe(Throwable error) {
        if (error == null) {
            return "unknown transport failure";
        }
        String message = error.getMessage();
        if (message == null || message.isBlank()) {
            return error.getClass().getSimpleName();
        }
        return error.getClass().getSimpleName() + ": " + message;
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

    private static String boardAsOf(JsonNode data) {
        return textAt(data, "latest_source_report_date");
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
