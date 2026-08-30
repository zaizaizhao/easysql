#!/usr/bin/env python
"""
End-to-end test for EasySql pipeline.

This script tests the complete flow:
1. Extract schema from PostgreSQL
2. Write to Neo4j
3. Write to Milvus
4. Verify data in both stores

Usage:
    # 先修改下面的配置，然后显式启用外部基础设施测试:
    EASYSQL_RUN_E2E=1 pytest tests/test_e2e_pipeline.py -v
"""

import os

import pytest

pytestmark = pytest.mark.skipif(
    os.getenv("EASYSQL_RUN_E2E") != "1",
    reason="E2E pipeline test requires local PostgreSQL, Neo4j, and Milvus; set EASYSQL_RUN_E2E=1",
)

# =============================================================================
# 🔧 修改这里的配置
# =============================================================================
# PostgreSQL 配置
PG_CONFIG = {
    "name": "TEST_DB",
    "db_type": "postgresql",
    "host": "localhost",  # ← 修改为你的 PostgreSQL 主机
    "port": 5432,  # ← 修改为你的端口
    "user": "postgres",  # ← 修改为你的用户名
    "password": "111111",  # ← 修改为你的密码
    "database": "agents",  # ← 修改为你的数据库名
    "system_type": "TEST",
    "description": "测试数据库",
}

# Neo4j 配置
NEO4J_CONFIG = {
    "uri": "bolt://localhost:7687",
    "user": "neo4j",
    "password": "all-in-rag",  # ← 与 docker-compose.yml 中的密码一致
}

# Milvus 配置
MILVUS_CONFIG = {
    "uri": "http://localhost:19530",
}


def _connect_postgresql():
    """Step 1: 测试 PostgreSQL 连接"""
    print("\n" + "=" * 60)
    print("Step 1: 测试 PostgreSQL 连接")
    print("=" * 60)

    from easysql.config import DatabaseConfig

    config = DatabaseConfig(**PG_CONFIG)
    print(f"连接字符串: {config.get_connection_string()}")

    from sqlalchemy import create_engine, text

    engine = create_engine(config.get_connection_string())

    with engine.connect() as conn:
        result = conn.execute(text("SELECT version()"))
        version = result.fetchone()[0]
        print("✅ PostgreSQL 连接成功!")
        print(f"   版本: {version[:50]}...")

    engine.dispose()
    return config


def _extract_schema(db_config):
    """Step 2: 测试 Schema 提取"""
    print("\n" + "=" * 60)
    print("Step 2: 测试 Schema 提取")
    print("=" * 60)

    from easysql.extractors.base import ExtractorFactory

    extractor = ExtractorFactory.create(db_config)
    print(f"✅ 创建提取器: {type(extractor).__name__}")

    db_meta = extractor.extract_all()

    print("✅ 提取完成!")
    print(f"   数据库: {db_meta.name}")
    print(f"   表数量: {len(db_meta.tables)}")
    total_columns = sum(len(t.columns) for t in db_meta.tables)
    print(f"   列数量: {total_columns}")
    print(f"   外键数量: {len(db_meta.foreign_keys)}")

    if db_meta.tables:
        print("\n   前 5 张表:")
        for table in db_meta.tables[:5]:
            print(f"     - {table.name} ({len(table.columns)} 列)")
            if table.chinese_name:
                print(f"       中文名: {table.chinese_name}")

    return db_meta


def _write_neo4j(db_meta):
    """Step 3: 测试 Neo4j 写入"""
    print("\n" + "=" * 60)
    print("Step 3: 测试 Neo4j 写入")
    print("=" * 60)

    from easysql.readers.neo4j_reader import Neo4jSchemaReader
    from easysql.repositories.neo4j_repository import Neo4jRepository
    from easysql.writers.neo4j_writer import Neo4jSchemaWriter

    repo = Neo4jRepository(
        uri=NEO4J_CONFIG["uri"],
        user=NEO4J_CONFIG["user"],
        password=NEO4J_CONFIG["password"],
    )
    repo.connect()

    writer = Neo4jSchemaWriter(repository=repo)
    reader = Neo4jSchemaReader(repository=repo)

    try:
        # 清空旧数据
        writer.clear_database(db_meta.name)
        print("✅ 已清空旧数据")

        # 写入新数据
        stats = writer.write_database(db_meta)
        print("✅ Neo4j 写入完成!")
        print(f"   表: {stats['tables']}")
        print(f"   列: {stats['columns']}")
        print(f"   外键: {stats['foreign_keys']}")

        # 验证：查询表数量
        table_count = reader.get_table_count()
        print(f"   验证 - 图中表节点: {table_count}")

        # 测试路径查找
        if len(db_meta.tables) >= 2:
            t1 = db_meta.tables[0].name
            t2 = db_meta.tables[1].name
            path = reader.find_join_path(t1, t2)
            if path:
                print(f"   路径测试: {t1} → {t2}")
                print(f"     经过表: {path['tables']}")
    except Exception as e:
        print(f"❌ Neo4j 写入失败: {e}")
        raise
    finally:
        repo.close()


def _write_milvus(db_meta):
    """Step 4: 测试 Milvus 写入"""
    print("\n" + "=" * 60)
    print("Step 4: 测试 Milvus 写入 (首次会下载 Embedding 模型，约 1.3GB)")
    print("=" * 60)

    from easysql.embeddings.embedding_service import EmbeddingService
    from easysql.readers.milvus_reader import MilvusSchemaReader
    from easysql.repositories.milvus_repository import MilvusRepository
    from easysql.writers.milvus_writer import MilvusVectorWriter

    # 初始化 Embedding 服务
    print("加载 Embedding 模型...")
    embedding_service = EmbeddingService.create_local(model_name="BAAI/bge-large-zh-v1.5")
    print(f"✅ Embedding 模型加载完成, 维度: {embedding_service.dimension}")

    repo = MilvusRepository(uri=MILVUS_CONFIG["uri"])
    repo.connect()

    writer = MilvusVectorWriter(
        repository=repo,
        embedding_service=embedding_service,
    )

    reader = MilvusSchemaReader(
        repository=repo,
        embedding_service=embedding_service,
    )

    try:
        # 创建 collections
        writer.create_table_collection(drop_existing=True)
        writer.create_column_collection(drop_existing=True)
        print("✅ Milvus Collections 创建完成")

        # 写入表向量
        tables_written = writer.write_table_embeddings(db_meta, batch_size=50)
        print(f"✅ 表向量写入: {tables_written}")

        # 写入列向量
        columns_written = writer.write_column_embeddings(db_meta, batch_size=50)
        print(f"✅ 列向量写入: {columns_written}")

        # 测试语义搜索
        print("\n   测试语义搜索...")
        test_queries = ["用户信息", "订单", "时间", "ID"]
        for query in test_queries:
            results = reader.search_tables(query, top_k=3)
            if results:
                print(f"   查询 '{query}':")
                for r in results[:2]:
                    print(f"     - {r['table_name']} (score: {r['score']:.3f})")

    except Exception as e:
        print(f"❌ Milvus 写入失败: {e}")
        raise
    finally:
        repo.close()


def test_e2e_pipeline():
    """Run the complete extraction and indexing flow against opted-in infrastructure."""
    print("\n" + "🚀 EasySql 端到端测试" + "\n")

    # Step 1: 测试 PostgreSQL 连接
    db_config = _connect_postgresql()

    # Step 2: 提取 Schema
    db_meta = _extract_schema(db_config)

    assert db_meta.tables, "没有提取到任何表，请检查数据库配置或权限"

    # Step 3: 写入 Neo4j
    _write_neo4j(db_meta)

    # Step 4: 写入 Milvus
    _write_milvus(db_meta)

    print("\n" + "=" * 60)
    print("🎉 全部测试通过!")
    print("=" * 60)
