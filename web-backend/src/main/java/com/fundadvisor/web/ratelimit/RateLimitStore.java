package com.fundadvisor.web.ratelimit;

import java.time.Duration;

public interface RateLimitStore {

    long increment(String key, Duration window);
}
