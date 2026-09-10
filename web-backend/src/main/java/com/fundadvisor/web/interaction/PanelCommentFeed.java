package com.fundadvisor.web.interaction;

import java.util.List;

public record PanelCommentFeed(
        String fund,
        int count,
        List<PanelCommentView> comments) {}
