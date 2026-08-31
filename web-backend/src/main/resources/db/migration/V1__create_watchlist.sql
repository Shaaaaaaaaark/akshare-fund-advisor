CREATE TABLE watchlist_item (
    id CHAR(36) NOT NULL,
    entity_type VARCHAR(16) NOT NULL,
    entity_code VARCHAR(64) NOT NULL,
    display_name VARCHAR(128) NOT NULL,
    created_at TIMESTAMP(6) NOT NULL,
    PRIMARY KEY (id),
    CONSTRAINT uq_watchlist_entity UNIQUE (entity_type, entity_code),
    INDEX idx_watchlist_created_at (created_at)
) ENGINE = InnoDB
  DEFAULT CHARACTER SET = utf8mb4
  COLLATE = utf8mb4_0900_ai_ci;
