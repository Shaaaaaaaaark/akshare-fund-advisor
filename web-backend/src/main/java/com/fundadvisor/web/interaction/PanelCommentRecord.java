package com.fundadvisor.web.interaction;

import java.time.Instant;

record PanelCommentRecord(
        String id,
        String content,
        String clientId,
        Instant createdAt) {}
