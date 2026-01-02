#!/usr/bin/env python
"""
完整链路测试：Query → Milvus(语义搜索) → Neo4j(关系补全)
验证从用户问题到相关表和 JOIN 路径的完整流程

运行：
    PYTHONPATH=. python tests/test_full_retrieval.py
"""

import os
from dotenv import load_dotenv

from easysql.embeddings import EmbeddingService
from easysql.writers.milvus_writer import MilvusVectorWriter
from easysql.writers.neo4j_writer import Neo4jSchemaWriter

# 从 .env 加载配置
load_dotenv()

MILVUS_URI = os.getenv("MILVUS_URI", "http://localhost:19530")
MILVUS_COLLECTION_PREFIX = os.getenv("MILVUS_COLLECTION_PREFIX", "medical")
NEO4J_URI = os.getenv("NEO4J_URI", "bolt://localhost:7687")
NEO4J_USER = os.getenv("NEO4J_USER", "neo4j")
NEO4J_PASSWORD = os.getenv("NEO4J_PASSWORD", "")
DB_NAME = "medical"  # 源数据库名，用于 Neo4j 过滤

# 测试问题列表
TEST_QUESTIONS = [
    ("简单", "患者信息", ["patient"]),
    ("中等", "查询住院超过7天的患者", ["admission", "patient"]),
    ("复杂", "查询患者的处方、用药和费用明细", ["patient", "prescription", "prescription_detail", "fee_record"]),
    ("复杂", "找出做过CT检查的住院患者及其主治医生", ["inspection_request", "admission", "patient", "doctor"]),
]


def main():
    print("=" * 70)
    print("完整链路测试：Query → Milvus → Neo4j")
    print("=" * 70)
    
    # 1. 初始化服务
    print("\n[1] 初始化 Embedding 服务...")
    embedding_service = EmbeddingService(model_name="BAAI/bge-large-zh-v1.5")
    
    print("[2] 连接 Milvus...")
    milvus = MilvusVectorWriter(
        uri=MILVUS_URI,
        embedding_service=embedding_service,
        collection_prefix=MILVUS_COLLECTION_PREFIX,
    )
    milvus.connect()
    
    print("[3] 连接 Neo4j...")
    neo4j = Neo4jSchemaWriter(
        uri=NEO4J_URI,
        user=NEO4J_USER,
        password=NEO4J_PASSWORD,
    )
    neo4j.connect()
    
    print(f"    Milvus Tables: {milvus.TABLE_COLLECTION}")
    print(f"    Neo4j Database: {neo4j.database}")
    
    # 2. 测试每个问题
    for level, question, expected_tables in TEST_QUESTIONS:
        print("\n" + "=" * 70)
        print(f"[{level}] 🔍 问题: {question}")
        print(f"📌 期望表: {expected_tables}")
        print("=" * 70)
        
        # Step 1: Milvus 语义搜索
        print("\n📋 Step 1: Milvus 语义搜索 - 相关表 (Top 5):")
        tables = milvus.search_tables(question, top_k=5)
        table_names = []
        if tables:
            for i, t in enumerate(tables, 1):
                table_names.append(t['table_name'])
                hit = "✅" if t['table_name'] in expected_tables else "  "
                print(f"   {hit} {i}. {t['table_name']} ({t['chinese_name'] or 'N/A'}) - Score: {t['score']:.4f}")
        else:
            print("   (无结果)")
        
        # 检查覆盖率
        found = set(table_names) & set(expected_tables)
        missing = set(expected_tables) - set(table_names)
        print(f"\n   覆盖率: {len(found)}/{len(expected_tables)} | 缺失: {list(missing) or '无'}")
        
        # Step 2: Neo4j 获取 JOIN 路径
        if len(table_names) >= 2:
            print(f"\n🔗 Step 2: Neo4j JOIN 路径 (连接上述 {len(table_names)} 张表):")
            try:
                join_edges = neo4j.find_join_paths_for_tables(
                    table_names[:5],  # 最多取5张表
                    max_hops=5,
                    db_name=DB_NAME,
                )
                if join_edges:
                    print(f"   找到 {len(join_edges)} 条 JOIN 边:")
                    for edge in join_edges:
                        print(f"   • {edge['fk_table']}.{edge['fk_column']} → {edge['pk_table']}.{edge['pk_column']}")
                else:
                    print("   (未找到 JOIN 路径，表可能没有直接外键关联)")
            except Exception as e:
                print(f"   ❌ 查询失败: {e}")
        
        # Step 3: 生成 Schema 概要
        print(f"\n📄 Step 3: Schema 概要 (可传给 LLM):")
        print("   ---")
        for t in tables[:3]:
            cols = milvus.search_columns(t['table_name'], top_k=5, table_filter=[t['table_name']])
            col_str = ", ".join([f"{c['column_name']}({c['data_type']})" for c in cols[:4]])
            print(f"   {t['table_name']} ({t['chinese_name'] or 'N/A'}): {col_str}...")
        print("   ---")
    
    # 3. 关闭连接
    milvus.close()
    neo4j.close()
    print("\n" + "=" * 70)
    print("测试完成！")
    print("=" * 70)


if __name__ == "__main__":
    main()
