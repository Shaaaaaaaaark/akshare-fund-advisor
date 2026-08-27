package com.fundadvisor.web.dataapi;

import com.fundadvisor.web.facts.ToolEnvelope;
import java.util.Map;
import reactor.core.publisher.Mono;

public interface DashboardToolCaller {

    Mono<ToolEnvelope> callTool(String tool, Map<String, Object> arguments);
}
