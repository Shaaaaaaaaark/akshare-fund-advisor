CREATE TABLE panel_interaction (
    id CHAR(36) NOT NULL,
    interaction_kind VARCHAR(24) NOT NULL,
    scope_key VARCHAR(64) NOT NULL,
    topic_key VARCHAR(64) NOT NULL,
    option_key VARCHAR(64) NOT NULL,
    client_id CHAR(36) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    updated_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_panel_interaction_client
        UNIQUE (interaction_kind, scope_key, topic_key, client_id),
    INDEX idx_panel_interaction_summary (
        interaction_kind,
        scope_key,
        topic_key,
        option_key
    )
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
