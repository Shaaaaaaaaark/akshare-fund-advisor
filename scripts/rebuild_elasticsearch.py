"""Rebuild the Elasticsearch document projection from PostgreSQL."""

from financial_agent.config import get_config
from financial_agent.rag.retrieval import ElasticsearchChunkIndex
from financial_agent.repositories import SQLRepository


def main() -> None:
    config = get_config()
    repository = SQLRepository(config)
    index = ElasticsearchChunkIndex(config)
    if not index.enabled:
        raise SystemExit("未配置 rag.elasticsearch_url")
    count = index.rebuild(repository)
    print(f"Elasticsearch 重建完成，写入 {count} 个文档分块。")


if __name__ == "__main__":
    main()
