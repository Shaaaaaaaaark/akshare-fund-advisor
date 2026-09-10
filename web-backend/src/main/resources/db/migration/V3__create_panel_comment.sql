CREATE TABLE panel_comment (
    id CHAR(36) NOT NULL,
    scope_key VARCHAR(64) NOT NULL,
    client_id CHAR(36) NOT NULL,
    content VARCHAR(280) NOT NULL,
    status VARCHAR(16) NOT NULL DEFAULT 'published',
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    INDEX idx_panel_comment_feed (scope_key, status, created_at DESC),
    INDEX idx_panel_comment_client (client_id, created_at DESC)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
