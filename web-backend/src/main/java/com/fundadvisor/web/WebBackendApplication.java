package com.fundadvisor.web;

import com.fundadvisor.web.config.BffProperties;
import com.fundadvisor.web.ratelimit.RateLimitProperties;
import java.time.Clock;
import org.mybatis.spring.annotation.MapperScan;
import org.springframework.boot.autoconfigure.task.TaskExecutionAutoConfiguration;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;
import org.springframework.core.task.AsyncTaskExecutor;
import org.springframework.core.task.SimpleAsyncTaskExecutor;

@SpringBootApplication
@MapperScan({"com.fundadvisor.web.watchlist", "com.fundadvisor.web.interaction"})
public class WebBackendApplication {

    public static void main(String[] args) {
        setServerPortFromLegacyAddress();
        SpringApplication.run(WebBackendApplication.class, args);
    }

    @Bean
    BffProperties bffProperties() {
        return BffProperties.fromEnvironment();
    }

    @Bean
    Clock clock() {
        return Clock.systemUTC();
    }

    @Bean
    RateLimitProperties rateLimitProperties() {
        return RateLimitProperties.fromEnvironment();
    }

    @Bean(name = TaskExecutionAutoConfiguration.APPLICATION_TASK_EXECUTOR_BEAN_NAME)
    AsyncTaskExecutor applicationTaskExecutor() {
        SimpleAsyncTaskExecutor executor = new SimpleAsyncTaskExecutor("fund-advisor-vt-");
        executor.setVirtualThreads(true);
        return executor;
    }

    private static void setServerPortFromLegacyAddress() {
        if (System.getenv("SERVER_PORT") != null || System.getProperty("server.port") != null) {
            return;
        }
        String address = System.getenv("WEB_BACKEND_ADDR");
        if (address == null || address.isBlank()) {
            return;
        }
        int separator = address.lastIndexOf(':');
        String port = separator >= 0 ? address.substring(separator + 1) : address;
        if (!port.isBlank()) {
            System.setProperty("server.port", port);
        }
    }
}
