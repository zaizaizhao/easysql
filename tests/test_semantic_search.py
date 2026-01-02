#!/usr/bin/env python
"""
最小化语义搜索测试脚本
验证：根据用户问题，找到相关的表和列

使用前确保：
1. 已执行 python main.py 写入数据到 Milvus
2. .env 中配置了 MILVUS_COLLECTION_PREFIX=medical (或与写入时一致)

运行：
    python tests/test_semantic_search.py
"""

from easysql.embeddings import EmbeddingService
from easysql.writers.milvus_writer import MilvusVectorWriter

# 配置 (与 .env 保持一致)
MILVUS_URI = "http://localhost:19530"
MILVUS_COLLECTION_PREFIX = "medical"  # 如果有前缀

# 测试问题列表 - 按复杂度分组
TEST_QUESTIONS = [
    # === 简单问题 (单表/单概念) ===
    ("简单", "患者信息"),
    ("简单", "处方药品明细"),
    ("简单", "费用结算记录"),
    
    # === 中等复杂 (带条件/动作) ===
    ("中等", "查询所有住院超过7天的患者"),
    ("中等", "今天门诊挂号的患者列表"),
    ("中等", "查看某个患者的所有检查报告"),
    
    # === 复杂问题 (多表/聚合/分析) ===
    ("复杂", "统计每个科室的门诊量和住院量，按月汇总"),
    ("复杂", "查询患者的处方、用药和费用明细"),
    ("复杂", "找出所有做过CT检查的住院患者及其主治医生"),
    ("复杂", "分析各科室的药品使用情况和抗生素使用比例"),
    
    # === 专业术语问题 ===
    ("专业", "ICD-10诊断编码对应的疾病"),
    ("专业", "医保报销比例和自费金额"),
]


def main():
    print("=" * 60)
    print("语义搜索测试 - 验证能否根据问题找到相关表和列")
    print("=" * 60)
    
    # 1. 初始化服务
    print("\n[1] 初始化 Embedding 服务...")
    embedding_service = EmbeddingService(model_name="BAAI/bge-large-zh-v1.5")
    
    print("[2] 连接 Milvus...")
    writer = MilvusVectorWriter(
        uri=MILVUS_URI,
        embedding_service=embedding_service,
        collection_prefix=MILVUS_COLLECTION_PREFIX,
    )
    writer.connect()
    
    print(f"    Table Collection: {writer.TABLE_COLLECTION}")
    print(f"    Column Collection: {writer.COLUMN_COLLECTION}")
    
    # 2. 测试每个问题
    for level, question in TEST_QUESTIONS:
        print("\n" + "-" * 60)
        print(f"[{level}] 🔍 问题: {question}")
        print("-" * 60)
        
        # 搜索相关表
        print("\n📋 相关表 (Top 5):")
        tables = writer.search_tables(question, top_k=5)
        if tables:
            for i, t in enumerate(tables, 1):
                print(f"   {i}. {t['table_name']} ({t['chinese_name'] or 'N/A'})")
                print(f"      Score: {t['score']:.4f} | DB: {t['database_name']}")
        else:
            print("   (无结果)")
        
        # 搜索相关列 (限定在找到的表中)
        if tables:
            table_names = [t['table_name'] for t in tables]
            print(f"\n📎 相关列 (在上述表中, Top 5):")
            columns = writer.search_columns(question, top_k=5, table_filter=table_names)
            if columns:
                for i, c in enumerate(columns, 1):
                    pk_fk = ""
                    if c.get('is_pk'): pk_fk += "🔑PK "
                    if c.get('is_fk'): pk_fk += "🔗FK "
                    print(f"   {i}. {c['table_name']}.{c['column_name']} ({c.get('chinese_name') or 'N/A'})")
                    print(f"      Type: {c['data_type']} {pk_fk}")
            else:
                print("   (无结果)")
    
    # 3. 关闭连接
    writer.close()
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
