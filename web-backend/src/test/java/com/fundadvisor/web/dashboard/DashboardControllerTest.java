package com.fundadvisor.web.dashboard;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.reactive.server.WebTestClient;

class DashboardControllerTest {

    private DashboardTestSupport.RecordingCaller caller;
    private WebTestClient client;

    @BeforeEach
    void setUp() {
        ObjectMapper mapper = new ObjectMapper();
        caller = new DashboardTestSupport.RecordingCaller(mapper);
        DashboardService service = new DashboardService(caller, mapper, DashboardTestSupport.properties());
        client = WebTestClient.bindToController(new DashboardController(service, DashboardTestSupport.properties()))
                .build();
    }

    @Test
    void fundProductRoutesToFourProductTools() {
        client.get()
                .uri("/api/dashboard/funds/000001/product?years=5")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.fund").isEqualTo("000001")
                .jsonPath("$.status").isEqualTo("available");

        assertThat(caller.calls)
                .extracting(DashboardTestSupport.Call::tool)
                .containsExactlyInAnyOrder(
                        DashboardService.FUND_ANALYZE_TOOL,
                        DashboardService.FUND_PROFILE_TOOL,
                        DashboardService.FUND_RATING_TOOL,
                        DashboardService.FUND_STATUS_TOOL);
        assertThat(caller.calls.stream()
                        .filter(call -> call.tool().equals(DashboardService.FUND_ANALYZE_TOOL))
                        .findFirst()
                        .orElseThrow()
                        .arguments())
                .containsEntry("years", 5);
    }

    @Test
    void etfRouteStaysSeparateFromFundProductRoute() {
        client.get()
                .uri("/api/dashboard/funds/510300?years=3&max_points=800")
                .exchange()
                .expectStatus().isOk();

        assertThat(caller.calls).hasSize(1);
        DashboardTestSupport.Call call = caller.calls.getFirst();
        assertThat(call.tool()).isEqualTo(DashboardService.ETF_DASHBOARD_TOOL);
        assertThat(call.arguments())
                .containsEntry("fund", "510300")
                .containsEntry("years", 3)
                .containsEntry("max_points", 800);
    }

    @Test
    void invalidFundParametersReturnBadRequestWithoutCallingDataApi() {
        for (String query : List.of("years=invalid", "years=10", "max_points=invalid", "max_points=20")) {
            caller.calls.clear();
            client.get()
                    .uri("/api/dashboard/funds/510300?" + query)
                    .exchange()
                    .expectStatus().isBadRequest();
            assertThat(caller.calls).isEmpty();
        }
    }

    @Test
    void invalidIndexParametersReturnBadRequestWithoutCallingDataApi() {
        for (String query : List.of("years=invalid", "years=1", "max_points=invalid", "max_points=20")) {
            caller.calls.clear();
            client.get()
                    .uri("/api/dashboard/indices/%E6%B2%AA%E6%B7%B1300?" + query)
                    .exchange()
                    .expectStatus().isBadRequest();
            assertThat(caller.calls).isEmpty();
        }
    }

    @Test
    void invalidStockParametersReturnBadRequestWithoutCallingDataApi() {
        for (String query : List.of("years=invalid", "years=20", "max_points=invalid", "max_points=20")) {
            caller.calls.clear();
            client.get()
                    .uri("/api/dashboard/stocks/600519?" + query)
                    .exchange()
                    .expectStatus().isBadRequest();
            assertThat(caller.calls).isEmpty();
        }
    }

    @Test
    void invalidParametersReturnJsonDetailSoTheFrontendCanRenderIt() {
        client.get()
                .uri("/api/dashboard/funds/510300?years=10")
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.detail").isEqualTo("years must be 1, 3 or 5");

        client.get()
                .uri("/api/dashboard/funds/search")
                .exchange()
                .expectStatus().isBadRequest()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.detail").isEqualTo("query is required");

        client.get()
                .uri("/api/dashboard/overview/unknown")
                .exchange()
                .expectStatus().isNotFound()
                .expectHeader().contentTypeCompatibleWith(MediaType.APPLICATION_JSON)
                .expectBody()
                .jsonPath("$.detail").isEqualTo("overview module not found");

        assertThat(caller.calls).isEmpty();
    }

    @Test
    void overviewModuleRefreshUsesConfiguredTarget() {
        client.get()
                .uri("/api/dashboard/overview/fund")
                .exchange()
                .expectStatus().isOk()
                .expectBody()
                .jsonPath("$.fund").isEqualTo("000001");

        assertThat(caller.calls).hasSize(1);
        assertThat(caller.calls.getFirst().tool()).isEqualTo(DashboardService.FUND_ANALYZE_TOOL);
    }
}
