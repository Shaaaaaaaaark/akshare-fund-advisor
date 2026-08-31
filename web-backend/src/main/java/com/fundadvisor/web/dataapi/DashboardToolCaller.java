package com.fundadvisor.web.dataapi;

import com.fundadvisor.web.facts.ToolEnvelope;
import java.util.Map;

public interface DashboardToolCaller {

    ToolEnvelope callTool(String tool, Map<String, Object> arguments);
}
