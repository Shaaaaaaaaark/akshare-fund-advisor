package com.fundadvisor.web.dashboard;

import java.util.List;

public record IndicesResponse(DataStatus status, List<IndexRow> rows) {}
