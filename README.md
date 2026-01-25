<div align="center">
  <img src="easysql_web/public/easysql_icon.svg" width="120" height="120" alt="EasySQL Logo" />
  <h1>EasySQL</h1>
  <p><strong>DDD 领域建模 × 知识图谱推理 × 向量语义检索</strong></p>
  <p>构建持续进化、越用越精准的企业级智能 SQL 引擎</p>

  <a href="https://zaizaizhao.github.io/easysql/">官网</a> •
  <a href="docs/README_EN.md">English</a> •
  <a href="https://github.com/zaizaizhao/easysql">GitHub</a>

[![Python 3.10+](https://img.shields.io/badge/python-3.10%2B-blue.svg)](https://www.python.org/downloads/)
[![License](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](https://opensource.org/licenses/Apache-2.0)
[![Code Style: Black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)

</div>

> ⚠️ **开发中** - 本项目仍在积极开发阶段，API 和功能可能会有变动。欢迎试用和反馈！

---

## 界面预览

![EasySQL 界面](docs/images/example_pic1.png)

---

## 为什么做这个？

企业数据库动辄几百张表，直接把 Schema 塞给 LLM 会遇到：
- Token 爆炸，塞不下
- 表名相似，LLM 选错
- 外键关系丢失，JOIN 写不对

EasySQL 的思路：
1. 用 **Neo4j** 构建知识图谱，存储表结构、外键关系，实现关系推理
2. 用 **Milvus** 做向量语义检索，深度理解业务意图
3. 用 **LangGraph** 编排智能体：意图理解 → Schema 检索 → SQL 生成 → 验证修复
4. 支持 **DDD 领域建模**，让 AI 理解业务上下文
5. **Few-Shot 学习** + 用户反馈闭环，越用越精准

## 核心特性

- **DDD 业务上下文**：深度理解业务领域，自动识别订单、库存、客户等核心概念
- **知识图谱驱动**：Neo4j 精准捕获外键、索引、约束，确保 JOIN 路径最优
- **Few-Shot 智能学习**：少量样本快速适配特定业务场景
- **越用越聪明**：持续学习用户反馈，查询准确率稳步提升
- **组合式架构**：检索、生成、验证、修复各环节可独立配置
- **语义向量检索**：「本月销量」自动关联 order_detail，告别关键词匹配
- **自愈式执行**：SQL 异常自动诊断修复，提升端到端成功率
- **全栈数据库**：MySQL、PostgreSQL、Oracle、SQL Server 一套方案通吃
- **全链路可观测**：LangFuse 集成，Token 消耗、推理耗时一目了然

## 快速开始

### 环境要求

- Python 3.10+
- Neo4j 4.0+
- Milvus 2.0+

### 安装

```bash
git clone https://github.com/zaizaizhao/easysql.git
cd easysql
pip install -r requirements.txt
```

### 配置

```bash
cp .env.example .env
# 编辑 .env，填入数据库连接信息和 API Key
```

主要配置项：
```ini
# 要分析的业务数据库
DB_HIS_TYPE=mysql
DB_HIS_HOST=localhost
DB_HIS_DATABASE=your_db

# 基础设施
NEO4J_URI=bolt://localhost:7687
MILVUS_URI=http://localhost:19530

# LLM（三选一，按优先级自动选择）
OPENAI_API_KEY=sk-xxx
# GOOGLE_API_KEY=xxx
# ANTHROPIC_API_KEY=xxx
```

### 初始化 Schema

首次运行需要把数据库 Schema 同步到 Neo4j 和 Milvus：

```bash
python main.py run
```

### 启动服务

```bash
# API 服务
uvicorn easysql_api.app:app --port 8000 --reload

# 前端（可选）
cd easysql_web && npm install && npm run dev
```

访问 http://localhost:8000/docs 查看 API 文档。

## 项目结构

```
easysql/           # 核心逻辑
  ├── config.py    # 配置管理
  ├── llm/         # LangGraph Agent
  ├── retrieval/   # Schema 检索
  └── extractors/  # 数据库 Schema 提取
easysql_api/       # FastAPI 接口
easysql_web/       # React 前端
```

## 开发

```bash
# 格式化
black .
ruff check . --fix

# 类型检查
mypy easysql

# 测试
pytest
```

## License

Apache 2.0
