package com.fundadvisor.web.dashboard;

import com.fundadvisor.web.config.BffProperties;
import java.util.Map;
import java.util.Set;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.PathVariable;
import org.springframework.web.bind.annotation.RequestParam;
import org.springframework.web.bind.annotation.RestController;

@RestController
public class DashboardController {

    private static final Set<Integer> INDEX_YEARS = Set.of(3, 5, 10, 20);
    private static final Set<Integer> FUND_YEARS = Set.of(1, 3, 5);
    private static final Set<Integer> STOCK_YEARS = Set.of(1, 3, 5, 10);

    private final DashboardService dashboard;
    private final BffProperties properties;

    public DashboardController(DashboardService dashboard, BffProperties properties) {
        this.dashboard = dashboard;
        this.properties = properties;
    }

    @GetMapping("/health")
    public Map<String, String> health() {
        return Map.of("status", "ok");
    }

    @GetMapping("/api/dashboard/overview")
    public ResponseEntity<?> overview() {
        return ResponseEntity.ok(dashboard.overview());
    }

    @GetMapping("/api/dashboard/overview/{module}")
    public ResponseEntity<?> overviewModule(@PathVariable String module) {
        BffProperties.OverviewTargets targets = properties.overview();
        return switch (module) {
            case "index" -> ResponseEntity.ok(dashboard.indexDetail(targets.index(), 10, 300));
            case "etf" -> ResponseEntity.ok(dashboard.etfDetail(targets.etf(), 3, 300));
            case "fund" -> ResponseEntity.ok(dashboard.fundOverview(targets.fund(), 3));
            case "stock" -> ResponseEntity.ok(dashboard.stockDetail(targets.stock(), 5, 300));
            default -> problemDetail(HttpStatus.NOT_FOUND, "overview module not found");
        };
    }

    @GetMapping("/api/dashboard/indices")
    public ResponseEntity<?> indices() {
        return ResponseEntity.ok(dashboard.indices());
    }

    @GetMapping("/api/dashboard/indices/{index}")
    public ResponseEntity<?> indexDetail(
            @PathVariable String index,
            @RequestParam(name = "years", required = false) String years,
            @RequestParam(name = "max_points", required = false) String maxPoints) {
        Integer parsedYears = parseOptionalInt(years, 0, "years must be 3, 5, 10 or 20");
        if (parsedYears == null || (parsedYears != 0 && !INDEX_YEARS.contains(parsedYears))) {
            return problemDetail(HttpStatus.BAD_REQUEST, "years must be 3, 5, 10 or 20");
        }
        Integer parsedMaxPoints = parseOptionalInt(maxPoints, 0, "max_points must be between 50 and 3000");
        if (parsedMaxPoints == null || (parsedMaxPoints != 0 && !validMaxPoints(parsedMaxPoints))) {
            return problemDetail(HttpStatus.BAD_REQUEST, "max_points must be between 50 and 3000");
        }
        return ResponseEntity.ok(dashboard.indexDetail(index, parsedYears, parsedMaxPoints));
    }

    @GetMapping("/api/dashboard/funds")
    public ResponseEntity<?> fundsRoot() {
        return problemDetail(HttpStatus.BAD_REQUEST, "fund path is required");
    }

    @GetMapping("/api/dashboard/funds/search")
    public ResponseEntity<?> fundSearch(
            @RequestParam(name = "query", required = false) String query,
            @RequestParam(name = "limit", required = false) String limit) {
        if (query == null || query.isBlank()) {
            return problemDetail(HttpStatus.BAD_REQUEST, "query is required");
        }
        Integer parsedLimit = parseOptionalInt(limit, 10, "limit must be between 1 and 20");
        if (parsedLimit == null || parsedLimit < 1 || parsedLimit > 20) {
            return problemDetail(HttpStatus.BAD_REQUEST, "limit must be between 1 and 20");
        }
        return ResponseEntity.ok(dashboard.fundSearch(query.trim(), parsedLimit));
    }

    @GetMapping("/api/dashboard/funds/{fund}")
    public ResponseEntity<?> etfDetail(
            @PathVariable String fund,
            @RequestParam(name = "years", required = false) String years,
            @RequestParam(name = "max_points", required = false) String maxPoints) {
        Integer parsedYears = parseOptionalInt(years, 3, "years must be 1, 3 or 5");
        if (parsedYears == null || !FUND_YEARS.contains(parsedYears)) {
            return problemDetail(HttpStatus.BAD_REQUEST, "years must be 1, 3 or 5");
        }
        Integer parsedMaxPoints = parseOptionalInt(maxPoints, 600, "max_points must be between 50 and 3000");
        if (parsedMaxPoints == null || !validMaxPoints(parsedMaxPoints)) {
            return problemDetail(HttpStatus.BAD_REQUEST, "max_points must be between 50 and 3000");
        }
        return ResponseEntity.ok(dashboard.etfDetail(fund, parsedYears, parsedMaxPoints));
    }

    @GetMapping("/api/dashboard/funds/{fund}/product")
    public ResponseEntity<?> fundProduct(
            @PathVariable String fund,
            @RequestParam(name = "years", required = false) String years) {
        Integer parsedYears = parseOptionalInt(years, 3, "years must be 1, 3 or 5");
        if (parsedYears == null || !FUND_YEARS.contains(parsedYears)) {
            return problemDetail(HttpStatus.BAD_REQUEST, "years must be 1, 3 or 5");
        }
        return ResponseEntity.ok(dashboard.fundProduct(fund, parsedYears));
    }

    @GetMapping("/api/dashboard/stocks")
    public ResponseEntity<?> stocksRoot() {
        return problemDetail(HttpStatus.BAD_REQUEST, "stock path is required");
    }

    @GetMapping("/api/dashboard/stocks/{stock}")
    public ResponseEntity<?> stockDetail(
            @PathVariable String stock,
            @RequestParam(name = "years", required = false) String years,
            @RequestParam(name = "max_points", required = false) String maxPoints) {
        Integer parsedYears = parseOptionalInt(years, 10, "years must be 1, 3, 5 or 10");
        if (parsedYears == null || !STOCK_YEARS.contains(parsedYears)) {
            return problemDetail(HttpStatus.BAD_REQUEST, "years must be 1, 3, 5 or 10");
        }
        Integer parsedMaxPoints = parseOptionalInt(maxPoints, 600, "max_points must be between 50 and 3000");
        if (parsedMaxPoints == null || !validMaxPoints(parsedMaxPoints)) {
            return problemDetail(HttpStatus.BAD_REQUEST, "max_points must be between 50 and 3000");
        }
        return ResponseEntity.ok(dashboard.stockDetail(stock, parsedYears, parsedMaxPoints));
    }

    private static Integer parseOptionalInt(String raw, int fallback, String _message) {
        if (raw == null || raw.isBlank()) {
            return fallback;
        }
        try {
            return Integer.parseInt(raw.trim());
        } catch (NumberFormatException ignored) {
            return null;
        }
    }

    private static boolean validMaxPoints(int value) {
        return value >= 50 && value <= 3000;
    }

    /** 前端只解析 JSON 的 detail 字段，4xx 必须返回 application/json。 */
    private static ResponseEntity<Map<String, String>> problemDetail(HttpStatus status, String detail) {
        return ResponseEntity.status(status)
                .contentType(MediaType.APPLICATION_JSON)
                .body(Map.of("detail", detail));
    }
}
