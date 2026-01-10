#!/usr/bin/env python
"""
测试 Schema Retrieval Service

验证完整的检索流程：Milvus → FK扩展 → 语义过滤 → 桥梁保护

运行：
    PYTHONPATH=. python tests/test_retrieval_service.py
"""

import os

from dotenv import load_dotenv

from easysql.embeddings import EmbeddingService
from easysql.readers.milvus_reader import MilvusSchemaReader
from easysql.readers.neo4j_reader import Neo4jSchemaReader
from easysql.repositories.milvus_repository import MilvusRepository
from easysql.repositories.neo4j_repository import Neo4jRepository
from easysql.retrieval import (
    RetrievalConfig,
    SchemaRetrievalService,
)

# 从 .env 加载配置
load_dotenv()

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_COLLECTION_PREFIX = os.getenv("MILVUS_COLLECTION_PREFIX", "medical")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
DB_NAME = "medical"

# 测试问题
TEST_QUESTIONS = [
    ("简单", "患者信息", ["patient"]),
    ("中等", "查询住院超过7天的患者", ["admission", "patient"]),
    (
        "复杂",
        "查询患者的处方、用药和费用明细",
        ["patient", "prescription", "prescription_detail", "fee_record"],
    ),
]


def main():
    print("=" * 70)
    print("Schema Retrieval Service 测试")
    print("=" * 70)

    # 1. 初始化服务
    print("\n[1] 初始化服务...")

    embedding_service = EmbeddingService(model_name="BAAI/bge-large-zh-v1.5")

    milvus_repo = MilvusRepository(
        uri=MILVUS_URI,
        collection_prefix=MILVUS_COLLECTION_PREFIX,
    )
    milvus_repo.connect()

    neo4j_repo = Neo4jRepository(
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
    )
    neo4j_repo.connect()

    milvus_reader = MilvusSchemaReader(
        repository=milvus_repo,
        embedding_service=embedding_service,
    )

    neo4j_reader = Neo4jSchemaReader(
        repository=neo4j_repo,
    )

    # 配置
    config = RetrievalConfig(
        search_top_k=5,
        expand_fk=True,
        expand_max_depth=1,
        semantic_filter_enabled=True,
        semantic_threshold=0.4,
        bridge_protection_enabled=True,
        bridge_max_hops=3,
        core_tables=["patient", "employee", "department"],
    )

    # 创建服务
    service = SchemaRetrievalService(
        milvus_reader=milvus_reader,
        neo4j_reader=neo4j_reader,
        config=config,
    )

    print(f"    配置: semantic_threshold={config.semantic_threshold}")
    print(f"    配置: bridge_protection={config.bridge_protection_enabled}")

    # 2. 测试每个问题
    for level, question, expected_tables in TEST_QUESTIONS:
        print("\n" + "=" * 70)
        print(f"[{level}] 🔍 问题: {question}")
        print(f"📌 期望表: {expected_tables}")
        print("=" * 70)

        # 调用服务
        result = service.retrieve(question=question, db_name=DB_NAME)

        # 显示结果
        print("\n📊 统计信息:")
        print(f"   Milvus 搜索: {result.stats.get('milvus_search', {}).get('count', 0)} 张表")

        if "fk_expansion" in result.stats:
            fk_stats = result.stats["fk_expansion"]
            print(f"   FK 扩展: {fk_stats['before']} → {fk_stats['after']} 张表")

        if "filters" in result.stats:
            filter_stats = result.stats["filters"]
            if "chain" in filter_stats:
                for name, stats in filter_stats["chain"].items():
                    if name == "semantic":
                        print(
                            f"   语义过滤: 保留 {stats.get('after', '?')} 张, 移除 {len(stats.get('removed', []))} 张"
                        )
                    elif name == "bridge":
                        print(f"   桥梁保护: 添加 {len(stats.get('bridges_added', []))} 张")

        print(f"\n📋 最终表 ({len(result.tables)} 张):")
        for i, t in enumerate(result.tables, 1):
            hit = "✅" if t in expected_tables else "  "
            print(f"   {hit} {i}. {t}")

        # 检查覆盖率
        found = set(result.tables) & set(expected_tables)
        missing = set(expected_tables) - set(result.tables)
        print(f"\n   覆盖率: {len(found)}/{len(expected_tables)} | 缺失: {list(missing) or '无'}")

        print(f"\n🔗 JOIN 路径 ({len(result.join_paths)} 条):")
        for edge in result.join_paths[:5]:
            print(
                f"   • {edge['fk_table']}.{edge['fk_column']} → {edge['pk_table']}.{edge['pk_column']}"
            )
        if len(result.join_paths) > 5:
            print(f"   ... 还有 {len(result.join_paths) - 5} 条")

    # 3. 关闭连接
    milvus_repo.close()
    neo4j_repo.close()

    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
