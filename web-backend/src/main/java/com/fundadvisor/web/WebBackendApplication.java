package com.fundadvisor.web;

import com.fundadvisor.web.config.BffProperties;
import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.context.annotation.Bean;

@SpringBootApplication
public class WebBackendApplication {

    public static void main(String[] args) {
        setServerPortFromLegacyAddress();
        SpringApplication.run(WebBackendApplication.class, args);
    }

    @Bean
    BffProperties bffProperties() {
        return BffProperties.fromEnvironment();
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
