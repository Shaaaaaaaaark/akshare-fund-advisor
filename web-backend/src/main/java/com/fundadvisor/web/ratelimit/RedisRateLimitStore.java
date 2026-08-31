package com.fundadvisor.web.ratelimit;

import java.time.Duration;
import java.util.List;
import org.springframework.data.redis.core.StringRedisTemplate;
import org.springframework.data.redis.core.script.DefaultRedisScript;
import org.springframework.stereotype.Component;

@Component
public class RedisRateLimitStore implements RateLimitStore {

    private static final DefaultRedisScript<Long> INCREMENT_WITH_EXPIRY =
            new DefaultRedisScript<>(
                    """
                    local current = redis.call('INCR', KEYS[1])
                    if current == 1 then
                        redis.call('EXPIRE', KEYS[1], ARGV[1])
                    end
                    return current
                    """,
                    Long.class);

    private final StringRedisTemplate redis;

    public RedisRateLimitStore(StringRedisTemplate redis) {
        this.redis = redis;
    }

    @Override
    public long increment(String key, Duration window) {
        Long value = redis.execute(
                INCREMENT_WITH_EXPIRY,
                List.of(key),
                Long.toString(window.toSeconds()));
        if (value == null) {
            throw new IllegalStateException("redis rate limit script returned no result");
        }
        return value;
    }
}
