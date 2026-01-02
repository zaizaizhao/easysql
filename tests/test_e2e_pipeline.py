#!/usr/bin/env python
"""
End-to-end test for EasySql pipeline.

This script tests the complete flow:
1. Extract schema from PostgreSQL
2. Write to Neo4j
3. Write to Milvus
4. Verify data in both stores

Usage:
    # 先修改下面的配置，然后运行:
    python tests/test_e2e_pipeline.py
"""

import sys
from pathlib import Path

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# =============================================================================
# 🔧 修改这里的配置
# =============================================================================
# PostgreSQL 配置
PG_CONFIG = {
    "name": "TEST_DB",
    "db_type": "postgresql",
    "host": "localhost",      # ← 修改为你的 PostgreSQL 主机
    "port": 5432,             # ← 修改为你的端口
    "user": "postgres",       # ← 修改为你的用户名
    "password": "111111",   # ← 修改为你的密码
    "database": "agents",    # ← 修改为你的数据库名
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


def test_postgresql_connection():
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
        print(f"✅ PostgreSQL 连接成功!")
        print(f"   版本: {version[:50]}...")
    
    engine.dispose()
    return config


def test_schema_extraction(db_config):
    """Step 2: 测试 Schema 提取"""
    print("\n" + "=" * 60)
    print("Step 2: 测试 Schema 提取")
    print("=" * 60)
    
    import easysql.extractors  # 触发注册
    from easysql.extractors.base import ExtractorFactory
    
    extractor = ExtractorFactory.create(db_config)
    print(f"✅ 创建提取器: {type(extractor).__name__}")
    
    db_meta = extractor.extract_all()
    
    print(f"✅ 提取完成!")
    print(f"   数据库: {db_meta.name}")
    print(f"   表数量: {len(db_meta.tables)}")
    total_columns = sum(len(t.columns) for t in db_meta.tables)
    print(f"   列数量: {total_columns}")
    print(f"   外键数量: {len(db_meta.foreign_keys)}")
    
    if db_meta.tables:
        print(f"\n   前 5 张表:")
        for table in db_meta.tables[:5]:
            print(f"     - {table.name} ({len(table.columns)} 列)")
            if table.chinese_name:
                print(f"       中文名: {table.chinese_name}")
    
    return db_meta


def test_neo4j_write(db_meta):
    """Step 3: 测试 Neo4j 写入"""
    print("\n" + "=" * 60)
    print("Step 3: 测试 Neo4j 写入")
    print("=" * 60)
    
    from easysql.writers.neo4j_writer import Neo4jSchemaWriter
    
    writer = Neo4jSchemaWriter(
        uri=NEO4J_CONFIG["uri"],
        user=NEO4J_CONFIG["user"],
        password=NEO4J_CONFIG["password"],
    )
    
    try:
        with writer:
            # 清空旧数据
            writer.clear_database(db_meta.name)
            print(f"✅ 已清空旧数据")
            
            # 写入新数据
            stats = writer.write_database(db_meta)
            print(f"✅ Neo4j 写入完成!")
            print(f"   表: {stats['tables']}")
            print(f"   列: {stats['columns']}")
            print(f"   外键: {stats['foreign_keys']}")
            
            # 验证：查询表数量
            table_count = writer.get_table_count()
            print(f"   验证 - 图中表节点: {table_count}")
            
            # 测试路径查找
            if len(db_meta.tables) >= 2:
                t1 = db_meta.tables[0].name
                t2 = db_meta.tables[1].name
                path = writer.find_join_path(t1, t2)
                if path:
                    print(f"   路径测试: {t1} → {t2}")
                    print(f"     经过表: {path['tables']}")
    except Exception as e:
        print(f"❌ Neo4j 写入失败: {e}")
        raise


def test_milvus_write(db_meta):
    """Step 4: 测试 Milvus 写入"""
    print("\n" + "=" * 60)
    print("Step 4: 测试 Milvus 写入 (首次会下载 Embedding 模型，约 1.3GB)")
    print("=" * 60)
    
    from easysql.embeddings.embedding_service import EmbeddingService
    from easysql.writers.milvus_writer import MilvusVectorWriter
    
    # 初始化 Embedding 服务
    print("加载 Embedding 模型...")
    embedding_service = EmbeddingService(model_name="BAAI/bge-large-zh-v1.5")
    print(f"✅ Embedding 模型加载完成, 维度: {embedding_service.dimension}")
    
    writer = MilvusVectorWriter(
        uri=MILVUS_CONFIG["uri"],
        embedding_service=embedding_service,
    )
    
    try:
        with writer:
            # 创建 collections
            writer.create_table_collection(drop_existing=True)
            writer.create_column_collection(drop_existing=True)
            print(f"✅ Milvus Collections 创建完成")
            
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
                results = writer.search_tables(query, top_k=3)
                if results:
                    print(f"   查询 '{query}':")
                    for r in results[:2]:
                        print(f"     - {r['table_name']} (score: {r['score']:.3f})")
                        
    except Exception as e:
        print(f"❌ Milvus 写入失败: {e}")
        raise


def main():
    """运行完整测试"""
    print("\n" + "🚀 EasySql 端到端测试" + "\n")
    
    try:
        # Step 1: 测试 PostgreSQL 连接
        db_config = test_postgresql_connection()
        
        # Step 2: 提取 Schema
        db_meta = test_schema_extraction(db_config)
        
        if not db_meta.tables:
            print("\n⚠️  警告: 没有提取到任何表，请检查数据库配置或权限")
            return
        
        # Step 3: 写入 Neo4j
        test_neo4j_write(db_meta)
        
        # Step 4: 写入 Milvus
        test_milvus_write(db_meta)
        
        print("\n" + "=" * 60)
        print("🎉 全部测试通过!")
        print("=" * 60)
        print("\n后续步骤:")
        print("  1. 访问 Neo4j Browser: http://localhost:7474")
        print("     运行 Cypher: MATCH (n) RETURN n LIMIT 50")
        print("  2. 使用 Milvus 语义搜索功能进行表/列检索")
        
    except Exception as e:
        print(f"\n❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
