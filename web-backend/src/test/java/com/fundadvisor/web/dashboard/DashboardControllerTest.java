package com.fundadvisor.web.dashboard;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.content;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.MediaType;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

class DashboardControllerTest {

    private DashboardTestSupport.RecordingCaller caller;
    private MockMvc mockMvc;

    @BeforeEach
    void setUp() {
        ObjectMapper mapper = new ObjectMapper();
        caller = new DashboardTestSupport.RecordingCaller(mapper);
        DashboardService service = new DashboardService(
                caller,
                mapper,
                DashboardTestSupport.properties(),
                DashboardTestSupport.DIRECT_EXECUTOR);
        mockMvc = MockMvcBuilders.standaloneSetup(
                        new DashboardController(service, DashboardTestSupport.properties()))
                .build();
    }

    @Test
    void fundProductRoutesToFourProductTools() throws Exception {
        mockMvc.perform(get("/api/dashboard/funds/000001/product").param("years", "5"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.fund").value("000001"))
                .andExpect(jsonPath("$.status").value("available"));

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
    void etfRouteStaysSeparateFromFundProductRoute() throws Exception {
        mockMvc.perform(get("/api/dashboard/funds/510300")
                        .param("years", "3")
                        .param("max_points", "800"))
                .andExpect(status().isOk());

        assertThat(caller.calls).hasSize(1);
        DashboardTestSupport.Call call = caller.calls.getFirst();
        assertThat(call.tool()).isEqualTo(DashboardService.ETF_DASHBOARD_TOOL);
        assertThat(call.arguments())
                .containsEntry("fund", "510300")
                .containsEntry("years", 3)
                .containsEntry("max_points", 800);
    }

    @Test
    void invalidFundParametersReturnBadRequestWithoutCallingDataApi() throws Exception {
        for (String query : List.of("years=invalid", "years=10", "max_points=invalid", "max_points=20")) {
            caller.calls.clear();
            mockMvc.perform(get("/api/dashboard/funds/510300?" + query))
                    .andExpect(status().isBadRequest());
            assertThat(caller.calls).isEmpty();
        }
    }

    @Test
    void invalidIndexParametersReturnBadRequestWithoutCallingDataApi() throws Exception {
        for (String query : List.of("years=invalid", "years=1", "max_points=invalid", "max_points=20")) {
            caller.calls.clear();
            mockMvc.perform(get("/api/dashboard/indices/{index}", "沪深300").queryParam(
                            query.substring(0, query.indexOf('=')),
                            query.substring(query.indexOf('=') + 1)))
                    .andExpect(status().isBadRequest());
            assertThat(caller.calls).isEmpty();
        }
    }

    @Test
    void invalidStockParametersReturnBadRequestWithoutCallingDataApi() throws Exception {
        for (String query : List.of("years=invalid", "years=20", "max_points=invalid", "max_points=20")) {
            caller.calls.clear();
            mockMvc.perform(get("/api/dashboard/stocks/600519?" + query))
                    .andExpect(status().isBadRequest());
            assertThat(caller.calls).isEmpty();
        }
    }

    @Test
    void invalidParametersReturnJsonDetailSoTheFrontendCanRenderIt() throws Exception {
        mockMvc.perform(get("/api/dashboard/funds/510300").param("years", "10"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.detail").value("years must be 1, 3 or 5"));

        mockMvc.perform(get("/api/dashboard/funds/search"))
                .andExpect(status().isBadRequest())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.detail").value("query is required"));

        mockMvc.perform(get("/api/dashboard/overview/unknown"))
                .andExpect(status().isNotFound())
                .andExpect(content().contentTypeCompatibleWith(MediaType.APPLICATION_JSON))
                .andExpect(jsonPath("$.detail").value("overview module not found"));

        assertThat(caller.calls).isEmpty();
    }

    @Test
    void overviewModuleRefreshUsesConfiguredTarget() throws Exception {
        mockMvc.perform(get("/api/dashboard/overview/fund"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.fund").value("000001"));

        assertThat(caller.calls).hasSize(1);
        assertThat(caller.calls.getFirst().tool()).isEqualTo(DashboardService.FUND_ANALYZE_TOOL);
    }

    @Test
    void marketPulseRoutesToTheAuditedMarketTool() throws Exception {
        mockMvc.perform(get("/api/dashboard/market-pulse"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.board").value("market-pulse"));

        assertThat(caller.calls).hasSize(1);
        assertThat(caller.calls.getFirst().tool()).isEqualTo(DashboardService.MARKET_PULSE_TOOL);
        assertThat(caller.calls.getFirst().arguments()).isEmpty();
    }
}
