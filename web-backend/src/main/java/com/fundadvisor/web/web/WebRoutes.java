package com.fundadvisor.web.web;

import com.fundadvisor.web.config.BffProperties;
import java.time.Duration;
import org.springframework.context.annotation.Configuration;
import org.springframework.web.servlet.config.annotation.AsyncSupportConfigurer;
import org.springframework.web.servlet.config.annotation.ResourceHandlerRegistry;
import org.springframework.web.servlet.config.annotation.WebMvcConfigurer;

@Configuration
public class WebRoutes implements WebMvcConfigurer {

    private final BffProperties properties;

    public WebRoutes(BffProperties properties) {
        this.properties = properties;
    }

    @Override
    public void addResourceHandlers(ResourceHandlerRegistry registry) {
        String assetsLocation = properties.staticDir()
                .toAbsolutePath()
                .normalize()
                .resolve("assets")
                .toUri()
                .toString();
        String location = assetsLocation.endsWith("/") ? assetsLocation : assetsLocation + "/";
        registry.addResourceHandler("/assets/**")
                .addResourceLocations(location)
                .setCachePeriod((int) Duration.ofDays(365).toSeconds());
    }

    @Override
    public void configureAsyncSupport(AsyncSupportConfigurer configurer) {
        configurer.setDefaultTimeout(Duration.ofMinutes(15).toMillis());
    }
}
