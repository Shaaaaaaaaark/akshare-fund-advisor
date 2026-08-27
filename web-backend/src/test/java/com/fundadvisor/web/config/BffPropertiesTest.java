package com.fundadvisor.web.config;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.Test;

class BffPropertiesTest {

    @Test
    void rejectsDataTimeoutBelowLowerBound() {
        for (Duration invalid : List.of(Duration.ZERO, Duration.ofSeconds(-5), Duration.ofMillis(500))) {
            assertThatThrownBy(() -> properties(invalid))
                    .isInstanceOf(IllegalArgumentException.class)
                    .hasMessageContaining("dataTimeout must be at least");
        }
    }

    @Test
    void keepsValidDataTimeout() {
        assertThat(properties(Duration.ofSeconds(90)).dataTimeout()).isEqualTo(Duration.ofSeconds(90));
        assertThat(properties(Duration.ofSeconds(BffProperties.MIN_DATA_TIMEOUT_SECONDS)).dataTimeout())
                .isEqualTo(Duration.ofSeconds(BffProperties.MIN_DATA_TIMEOUT_SECONDS));
    }

    @Test
    void fromEnvironmentClampsDataTimeoutToLowerBound() {
        BffProperties properties = BffProperties.fromEnvironment();

        assertThat(properties.dataTimeout().getSeconds())
                .isGreaterThanOrEqualTo(BffProperties.MIN_DATA_TIMEOUT_SECONDS);
    }

    private static BffProperties properties(Duration dataTimeout) {
        return new BffProperties(
                "http://data-api",
                "http://agent-api",
                Path.of("web/dist"),
                List.of("沪深300"),
                10,
                2,
                dataTimeout,
                new BffProperties.OverviewTargets("沪深300", "510310", "000001", "600519"));
    }
}
