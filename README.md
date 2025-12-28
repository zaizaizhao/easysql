# EasySql

Enterprise Text2SQL 元数据流水线，使用 Neo4j 和 Milvus 构建数据库 Schema 的图关系和语义向量。

## 功能特性

- 🗄️ **多数据库支持**: MySQL, PostgreSQL (可扩展)
- 🕸️ **Neo4j 图存储**: 表/列节点、外键关系
- 🔍 **Milvus 向量搜索**: 表级和列级语义嵌入
- ⚙️ **企业级设计**: 适配器模式、工厂模式、依赖注入
- 🔧 **环境变量配置**: 通过 .env 文件管理所有配置

## 项目结构

```
EasySql/
├── easysql/                       # 主包
│   ├── config.py                  # 配置加载器
│   ├── models/                    # 数据模型
│   │   ├── base.py               # 基础抽象类
│   │   └── schema.py             # Schema元数据模型
│   ├── extractors/               # 数据库Schema提取器
│   │   ├── base.py               # 抽象基类 + 工厂
│   │   ├── mysql.py              # MySQL适配器
│   │   └── postgresql.py         # PostgreSQL适配器
│   ├── writers/                  # 数据写入器
│   │   ├── neo4j_writer.py       # Neo4j图写入
│   │   └── milvus_writer.py      # Milvus向量写入
│   ├── embeddings/               # 嵌入模型
│   │   └── embedding_service.py  # 向量化服务
│   ├── pipeline/                 # 流水线编排
│   │   └── schema_pipeline.py    # Schema处理流水线
│   └── utils/                    # 工具类
│       └── logger.py             # 日志配置
├── tests/                        # 测试目录
├── .env.example                  # 环境变量模板
├── pyproject.toml                # 项目配置
├── requirements.txt              # 依赖清单
└── main.py                       # CLI入口
```

## 快速开始

### 1. 安装依赖

```bash
cd EasySql
pip install -r requirements.txt
```

### 2. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env 文件，填写实际配置
```

### 3. 运行流水线

```bash
# 运行完整流水线
python main.py run

# 仅提取 Schema（不写入 Neo4j/Milvus）
python main.py run --no-neo4j --no-milvus

# 清空现有数据后重新写入
python main.py run --drop-existing

# 显示当前配置
python main.py config

# 显示版本
python main.py version
```

## 配置说明

在 `.env` 文件中配置以下内容：

```env
# Neo4j
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_password

# Milvus
MILVUS_URI=http://localhost:19530

# 嵌入模型
EMBEDDING_MODEL=BAAI/bge-large-zh-v1.5

# 数据库配置（可配置多个）
DB_HIS_TYPE=mysql
DB_HIS_HOST=localhost
DB_HIS_PORT=3306
DB_HIS_USER=root
DB_HIS_PASSWORD=password
DB_HIS_DATABASE=his_db
DB_HIS_SYSTEM_TYPE=HIS
```

## 架构设计

### 数据流

```
源数据库 (MySQL/PostgreSQL)
       │
       ▼
┌─────────────────────────┐
│    Schema Extractor     │  (适配器模式)
│   - MySQL Extractor     │
│   - PostgreSQL Extractor│
└───────────┬─────────────┘
            │
            ▼
┌─────────────────────────┐
│   Metadata Models       │  (Pydantic)
│   - DatabaseMeta        │
│   - TableMeta           │
│   - ColumnMeta          │
└───────────┬─────────────┘
            │
      ┌─────┴─────┐
      ▼           ▼
┌───────────┐ ┌───────────┐
│  Neo4j    │ │  Milvus   │
│  Writer   │ │  Writer   │
└───────────┘ └───────────┘
```

### Neo4j 图结构

```
(Database)-[:HAS_TABLE]->(Table)-[:HAS_COLUMN]->(Column)
(Table)-[:FOREIGN_KEY {fk_column, pk_column}]->(Table)
```

### Milvus 集合

- `table_embeddings`: 表级语义向量
- `column_embeddings`: 列级语义向量

## 扩展开发

### 添加新数据库支持

1. 在 `extractors/` 下创建新的提取器类
2. 继承 `BaseSchemaExtractor`
3. 实现 `connect()`, `disconnect()`, `extract_tables()`, `extract_foreign_keys()` 方法
4. 使用 `ExtractorFactory.register()` 注册

```python
from easysql.extractors.base import BaseSchemaExtractor, ExtractorFactory

class OracleSchemaExtractor(BaseSchemaExtractor):
    @property
    def db_type(self) -> DatabaseType:
        return DatabaseType.ORACLE
    
    # 实现抽象方法...

ExtractorFactory.register("oracle", OracleSchemaExtractor)
```

## License

MIT
