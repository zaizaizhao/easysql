#!/usr/bin/env python
"""
完整链路测试：使用 SchemaRetrievalService 进行智能检索，并集成 ContextBuilder 生成 LLM 上下文，最后调用 LLM 生成 SQL

测试完整的检索流程：
    Query → Milvus搜索 → FK扩展 → 语义过滤 → 桥梁保护 → LLM裁剪(可选) → Context构建 → LLM生成SQL

运行：
    PYTHONPATH=. python tests/test_full_retrieval.py
"""

import os
import re

from dotenv import load_dotenv
from openai import OpenAI

from easysql.context import ContextBuilder, ContextInput
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
DB_NAME = "medical"  # 源数据库名，用于隔离

# LLM 配置
LLM_API_BASE = os.getenv("LLM_API_BASE", "https://api.moonshot.cn/v1")
LLM_API_KEY = os.getenv("LLM_API_KEY", "")
LLM_MODEL = os.getenv("LLM_SQL_MODEL", "kimi-k2-0905-preview")

# 测试问题列表
TEST_QUESTIONS = [
    ("简单", "患者信息", ["patient"]),
    ("中等", "查询住院超过7天的患者", ["admission", "patient"]),
    (
        "复杂",
        "查询患者的处方、用药和费用明细",
        ["patient", "prescription", "prescription_detail", "fee_record"],
    ),
    (
        "复杂",
        "找出做过CT检查的住院患者及其主治医生",
        ["inspection_request", "admission", "patient", "employee"],
    ),
]


def generate_sql(
    client: OpenAI,
    system_prompt: str,
    user_prompt: str,
    model: str = LLM_MODEL,
) -> str:
    """
    调用 LLM 生成 SQL 语句。

    Args:
        client: OpenAI 客户端
        system_prompt: 系统提示词
        user_prompt: 用户提示词（包含 schema 和问题）
        model: 模型名称

    Returns:
        生成的 SQL 语句
    """
    try:
        response = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            temperature=0.0,  # 使用确定性输出
            max_tokens=1024,
        )

        content = response.choices[0].message.content

        # 提取 SQL（处理 markdown 代码块）
        sql = content.strip()

        # 如果返回的是 markdown 代码块，提取其中的 SQL
        if "```sql" in sql.lower():
            match = re.search(r"```sql\s*(.*?)\s*```", sql, re.DOTALL | re.IGNORECASE)
            if match:
                sql = match.group(1).strip()
        elif "```" in sql:
            match = re.search(r"```\s*(.*?)\s*```", sql, re.DOTALL)
            if match:
                sql = match.group(1).strip()

        return sql

    except Exception as e:
        return f"-- Error: {str(e)}"


def main():
    print("=" * 70)
    print("SchemaRetrievalService 完整链路测试")
    print("=" * 70)

    # 1. 初始化服务
    print("\n[1] 初始化服务...")
    embedding_service = EmbeddingService.create_local(model_name="BAAI/bge-large-zh-v1.5")

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

    # 初始化 LLM 客户端
    llm_client = None
    if LLM_API_KEY:
        llm_client = OpenAI(
            api_key=LLM_API_KEY,
            base_url=LLM_API_BASE,
        )
        print(f"    ✅ LLM 客户端已初始化 (model: {LLM_MODEL})")
    else:
        print("    ⚠️ LLM_API_KEY 未设置，跳过 SQL 生成")

    # 2. 创建检索服务 (使用配置)
    config = RetrievalConfig(
        # Milvus 搜索
        search_top_k=5,
        # FK 扩展
        expand_fk=True,
        expand_max_depth=1,
        # 语义过滤 (关键配置)
        semantic_filter_enabled=False,
        semantic_threshold=0.55,
        semantic_min_tables=3,
        # 核心表白名单 (这些表不会被过滤)
        # core_tables=["patient", "employee", "department"],
        # 桥梁表保护
        bridge_protection_enabled=True,
        bridge_max_hops=3,
        # LLM 裁剪 (可选，需要设置 API key)
        llm_filter_enabled=True,
        llm_api_key=os.getenv("LLM_API_KEY"),
        llm_api_base=os.getenv("LLM_API_BASE", "https://api.moonshot.cn/v1"),
        llm_filter_model=os.getenv("LLM_FILTER_MODEL", "kimi-k2-0905-preview"),
        llm_filter_max_tables=8,
    )

    service = SchemaRetrievalService(
        milvus_reader=milvus_reader,
        neo4j_reader=neo4j_reader,
        config=config,
    )

    # 显示配置
    print("\n[2] 检索配置:")
    print(f"    🔍 search_top_k: {config.search_top_k}")
    print(f"    🔄 expand_fk: {config.expand_fk}")
    print(
        f"    📊 semantic_filter: {config.semantic_filter_enabled} (threshold={config.semantic_threshold})"
    )
    print(f"    🔗 bridge_protection: {config.bridge_protection_enabled}")
    print(f"    🤖 llm_filter: {config.llm_filter_enabled}")
    print(f"    📌 core_tables: {config.core_tables}")

    # 3. 测试每个问题
    total_coverage = 0
    total_expected = 0

    for level, question, expected_tables in TEST_QUESTIONS:
        print("\n" + "=" * 70)
        print(f"[{level}] 🔍 问题: {question}")
        print(f"📌 期望表: {expected_tables}")
        print("=" * 70)

        # 执行检索
        result = service.retrieve(question=question, db_name=DB_NAME)

        # 显示统计
        stats = result.stats

        # Milvus 搜索统计
        milvus_stats = stats.get("milvus_search", {})
        print(f"\n📋 Step 1: Milvus 语义搜索 ({milvus_stats.get('count', 0)} 张表)")
        milvus_tables = milvus_stats.get("tables", [])
        milvus_scores = milvus_stats.get("scores", {})
        for i, t in enumerate(milvus_tables[:5], 1):
            hit = "✅" if t in expected_tables else "  "
            score = milvus_scores.get(t, 0)
            print(f"   {hit} {i}. {t} (score: {score:.4f})")

        # FK 扩展统计
        fk_stats = stats.get("fk_expansion", {})
        if fk_stats:
            print(
                f"\n🔄 Step 2: FK 扩展 ({fk_stats.get('before', 0)} → {fk_stats.get('after', 0)} 张)"
            )
            added = fk_stats.get("added", [])
            if added:
                print(f"   新增: {added[:8]}{'...' if len(added) > 8 else ''}")

        # 过滤统计
        filter_stats = stats.get("filters", {})
        if "chain" in filter_stats:
            chain = filter_stats["chain"]

            # 语义过滤
            if "semantic" in chain:
                sem = chain["semantic"]
                print("\n📊 Step 3: 语义过滤")
                print(
                    f"   保留: {sem.get('after', '?')} 张 (必保: {sem.get('must_keep', 0)}, 高分: {sem.get('kept_by_score', 0)})"
                )
                removed = sem.get("removed", [])
                if removed:
                    print(f"   移除低分表: {removed[:5]}{'...' if len(removed) > 5 else ''}")

            # 桥梁保护
            if "bridge" in chain:
                bridge = chain["bridge"]
                bridges_added = bridge.get("bridges_added", [])
                if bridges_added:
                    print(f"\n🔗 Step 4: 桥梁保护 (添加 {len(bridges_added)} 张)")
                    print(f"   桥梁表: {bridges_added}")

            # LLM 裁剪
            if "llm" in chain:
                llm = chain["llm"]
                if llm.get("action") == "llm_filter":
                    print("\n🤖 Step 5: LLM 裁剪")
                    print(f"   模型: {llm.get('model', 'N/A')}")
                    print(f"   {llm.get('before', '?')} → {llm.get('after', '?')} 张表")
                elif llm.get("action") == "skipped":
                    print(f"\n🤖 Step 5: LLM 裁剪 (跳过: {llm.get('reason', 'N/A')})")

        # 最终结果
        print(f"\n📋 最终表列表 ({len(result.tables)} 张):")
        for i, t in enumerate(result.tables, 1):
            hit = "✅" if t in expected_tables else "  "
            print(f"   {hit} {i}. {t}")

        # 覆盖率检查
        found = set(result.tables) & set(expected_tables)
        missing = set(expected_tables) - set(result.tables)
        coverage = len(found) / len(expected_tables) * 100
        total_coverage += len(found)
        total_expected += len(expected_tables)

        print(
            f"\n   覆盖率: {len(found)}/{len(expected_tables)} ({coverage:.0f}%) | 缺失: {list(missing) or '无'}"
        )

        # JOIN 路径
        if result.join_paths:
            print(f"\n🔗 JOIN 路径 ({len(result.join_paths)} 条):")
            for edge in result.join_paths[:5]:
                print(
                    f"   • {edge['fk_table']}.{edge['fk_column']} → {edge['pk_table']}.{edge['pk_column']}"
                )
            if len(result.join_paths) > 5:
                print(f"   ... 还有 {len(result.join_paths) - 5} 条")

        # ===== Context 构建 =====
        print(f"\n{'=' * 70}")
        print("📝 Context 构建测试")
        print("=" * 70)

        # 创建 ContextInput
        context_input = ContextInput(
            question=question,
            retrieval_result=result,
            db_name=DB_NAME,
        )

        # 使用默认的 ContextBuilder 构建上下文
        builder = ContextBuilder.default()
        context_output = builder.build(context_input)

        # 输出 Context 统计
        print("\n📊 Context 统计:")
        print(f"   总 Token 数: {context_output.total_tokens}")
        print(f"   Section 数量: {len(context_output.sections)}")
        for section in context_output.sections:
            print(f"     - {section.name}: {section.token_count} tokens")

        # 输出 System Prompt
        print(f"\n{'─' * 70}")
        print("🤖 System Prompt:")
        print("─" * 70)
        print(context_output.system_prompt)

        # 输出 User Prompt
        print(f"\n{'─' * 70}")
        print("👤 User Prompt:")
        print("─" * 70)
        print(context_output.user_prompt)
        print("─" * 70)

        # ===== LLM 生成 SQL =====
        if llm_client:
            print(f"\n{'=' * 70}")
            print("🧠 LLM SQL 生成")
            print("=" * 70)

            sql = generate_sql(
                client=llm_client,
                system_prompt=context_output.system_prompt,
                user_prompt=context_output.user_prompt,
                model=LLM_MODEL,
            )

            print("\n📝 生成的 SQL:")
            print("─" * 70)
            print(sql)
            print("─" * 70)

    # 4. 总结
    total_pct = total_coverage / total_expected * 100 if total_expected > 0 else 0
    print("\n" + "=" * 70)
    print(f"测试完成！总覆盖率: {total_coverage}/{total_expected} ({total_pct:.0f}%)")
    print("=" * 70)

    # 5. 关闭连接
    milvus_repo.close()
    neo4j_repo.close()

if __name__ == "__main__":
    main()
