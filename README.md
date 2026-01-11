# EasySQL

企业级 Text2SQL 解决方案。通过 Neo4j 构建数据库 Schema 知识图谱，通过 Milvus 实现语义检索，结合 LLM 将自然语言转换为 SQL。

## 功能特性

- **多数据库支持** - MySQL、PostgreSQL、Oracle、SQL Server
- **Schema 知识图谱** - Neo4j 存储表结构与外键关系
- **语义向量检索** - Milvus 实现表/列级别的语义搜索
- **智能 Text2SQL** - LangGraph 驱动的 LLM Agent，支持多轮澄清与 SQL 自动修复

## 快速开始

### 安装

```bash
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，配置数据库连接、Neo4j、Milvus、LLM API 等
```

### 运行 Schema 提取

```bash
# 提取数据库 Schema 并写入 Neo4j + Milvus
python main.py run

# 仅提取 Schema（不写入存储）
python main.py run --no-neo4j --no-milvus
```

### 运行 Text2SQL Agent

```bash
python examples/run_agent.py
```

交互示例：

```
[his] > 查询今天门诊挂号量最多的前10个科室
--- Processing ---
Generated SQL:
==================================================
SELECT d.dept_name, COUNT(*) as visit_count
FROM outpatient_registration r
JOIN department d ON r.dept_id = d.dept_id
WHERE DATE(r.reg_time) = CURDATE()
GROUP BY d.dept_id
ORDER BY visit_count DESC
LIMIT 10;
==================================================
✓ Validation Passed
```

## License

MIT
