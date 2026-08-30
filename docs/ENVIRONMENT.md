# EasySQL Environment Variables

This project loads configuration from a `.env` file and process environment variables. The
settings schema is defined in `easysql/configuration/` and re-exported from `easysql/config.py`.

By default, EasySQL reads `.env` from the project root (template: `.env.example`). You can
override the env file path via CLI:

```bash
python main.py run --env /path/to/.env
```

Notes:
- Settings are case-insensitive (`case_sensitive=False`).
- Extra env vars are ignored or kept as extra fields (`extra=allow`).
- Do not put real secrets in docs; use placeholders.

---

## 1) Project / Control Plane

| Variable | Default | Description |
| --- | --- | --- |
| `PROJECT_NAMESPACE` | `default` | Application namespace for Milvus collection prefixes and Neo4j logical scope. Does not replace `NEO4J_DATABASE`. Env-only (not editable via the config API): changing it requires a restart plus reindexing, otherwise retrieval points at empty collections. |
| `POSTGRES_URI` | `postgresql://postgres:postgres@localhost:5432/easysql` | PostgreSQL control-plane URI. Code derives async SQLAlchemy and psycopg DSNs from this value. |
| `POSTGRES_POOL_SIZE` | `10` | Startup-only control-plane SQLAlchemy pool size |
| `POSTGRES_MAX_OVERFLOW` | `20` | Startup-only overflow connections for the control-plane pool |
| `POSTGRES_POOL_TIMEOUT` | `30` | Seconds to wait when checking out a control-plane connection |
| `POSTGRES_POOL_RECYCLE` | `3600` | Seconds before recycling a pooled control-plane connection |
| `POSTGRES_POOL_PRE_PING` | `true` | Validate pooled control-plane connections before use |

`POSTGRES_POOL_*` values are read at API startup. They are intentionally not frontend runtime
configuration because changing them requires recreating the SQLAlchemy engine.

---

## 2) Neo4j

| Variable | Default | Description |
| --- | --- | --- |
| `NEO4J_URI` | `bolt://localhost:7687` | Neo4j connection URI |
| `NEO4J_USER` | `neo4j` | Username |
| `NEO4J_PASSWORD` | empty | Password |
| `NEO4J_DATABASE` | `neo4j` | Database name (Neo4j 4.0+) |

Docker Compose (container env only):
- `NEO4J_AUTH`: `neo4j/<password>`
- `NEO4J_PLUGINS`: e.g. `["apoc"]`

---

## 3) Milvus

| Variable | Default | Description |
| --- | --- | --- |
| `MILVUS_URI` | `http://localhost:19530` | Milvus endpoint |
| `MILVUS_TOKEN` | empty | Milvus auth token (optional) |

Collection prefixes are derived from `PROJECT_NAMESPACE`.

Docker Compose (container env only):
- `ETCD_USE_EMBED=true`, `ETCD_DATA_DIR=/var/lib/milvus/etcd`
- `COMMON_STORAGETYPE=local`

---

## 4) Embedding Model

| Variable | Default | Description |
| --- | --- | --- |
| `EMBEDDING_PROVIDER` | `local` | `local` / `openai_api` / `tei` |
| `EMBEDDING_MODEL` | `BAAI/bge-large-zh-v1.5` | Model name/ID |
| `EMBEDDING_DIMENSION` | `1024` | Vector dimension |
| `EMBEDDING_API_BASE` | empty | Required for `openai_api`/`tei` |
| `EMBEDDING_API_KEY` | empty | API key (optional) |
| `EMBEDDING_DEVICE` | empty | `cpu` / `cuda` / empty for auto |
| `EMBEDDING_CACHE_DIR` | empty | Local model cache dir |

API request timeout is fixed at 60 seconds in code.

---

## 5) Source Databases (dynamic DB_<NAME>_*)

Any database is activated by setting `DB_<NAME>_TYPE`. Multiple databases are supported
(e.g., `DB_HIS_*`, `DB_LIS_*`).

| Variable | Description | Default |
| --- | --- | --- |
| `DB_<NAME>_TYPE` | Database type | required; examples: `mysql`, `postgresql`, `oracle`, `sqlserver` |
| `DB_<NAME>_HOST` | Host | `localhost` |
| `DB_<NAME>_PORT` | Port | `3306` (set explicitly for non-MySQL) |
| `DB_<NAME>_USER` | User | `root` |
| `DB_<NAME>_PASSWORD` | Password | empty |
| `DB_<NAME>_DATABASE` | Database name | empty |
| `DB_<NAME>_SCHEMA` | Schema | empty (defaults: MySQL=DB name, PostgreSQL=public, Oracle=USER, SQL Server=dbo) |
| `DB_<NAME>_SYSTEM_TYPE` | Business system type | `UNKNOWN` |
| `DB_<NAME>_DESCRIPTION` | Business system description | empty |

Extractor registrations include `mysql`, `postgresql`, `oracle`, `sqlserver`.

---

## 6) Pipeline Flags

Pipeline steps are controlled via CLI flags (`--no-extract`, `--no-neo4j`, `--no-milvus`),
not environment variables. Batch size is fixed at 1000 in code.

---

## 7) Logging

| Variable | Default | Description |
| --- | --- | --- |
| `LOG_LEVEL` | `INFO` | `DEBUG/INFO/WARNING/ERROR/CRITICAL` |
| `LOG_FILE` | empty | Log file path (e.g. `logs/easysql.log`) |

---

## 8) Schema Retrieval (Text2SQL)

Search:

| Variable | Default | Description |
| --- | --- | --- |
| `RETRIEVAL_SEARCH_TOP_K` | `5` | Tables returned from Milvus |
| `RETRIEVAL_EXPAND_FK` | `true` | Expand by FK relations |
| `RETRIEVAL_EXPAND_MAX_DEPTH` | `1` | FK expansion depth |

Semantic filter:

| Variable | Default | Description |
| --- | --- | --- |
| `SEMANTIC_FILTER_ENABLED` | `true` | Enable semantic filtering |
| `SEMANTIC_FILTER_THRESHOLD` | `0.4` | Minimum relevance threshold |
| `SEMANTIC_FILTER_MIN_TABLES` | `3` | Minimum tables to keep |
| `CORE_TABLES` | *(empty)* | Core tables kept through filtering (comma-separated). Empty disables the whitelist. |

Bridge protection:

| Variable | Default | Description |
| --- | --- | --- |
| `BRIDGE_PROTECTION_ENABLED` | `true` | Protect bridge tables |

Bridge max hops is an internal retrieval constant (`3`), not an editable environment variable.

---

## 9) LLM Filter (Retrieval Layer)

| Variable | Default | Description |
| --- | --- | --- |
| `LLM_FILTER_ENABLED` | `false` | Enable LLM-based filtering |
| `LLM_FILTER_MAX_TABLES` | `8` | Max tables after filtering |
| `LLM_FILTER_MODEL` | `deepseek-chat` | Filter model |

The LLM filter reuses the OpenAI-compatible generation settings (`OPENAI_API_KEY` and
`OPENAI_API_BASE`) instead of separate retrieval-layer credentials.

---

## 10) LLM Layer (LangGraph Agent)

| Variable | Default | Description |
| --- | --- | --- |
| `QUERY_MODE` | `plan` | `plan` (interactive) or `fast` |
| `OPENAI_API_KEY` | empty | OpenAI API key |
| `OPENAI_API_BASE` | `https://api.openai.com/v1` | OpenAI API base |
| `GOOGLE_API_KEY` | empty | Google Gemini API key |
| `ANTHROPIC_API_KEY` | empty | Anthropic API key |
| `OPENAI_LLM_MODEL` | `gpt-4o` | OpenAI model name |
| `GOOGLE_LLM_MODEL` | empty | Google model name |
| `ANTHROPIC_LLM_MODEL` | empty | Anthropic model name |
| `MODEL_PLANNING` | empty | Model for analyze/clarify phase |
| `LLM_TEMPERATURE` | `0.0` | Sampling temperature (`0.0` ~ `2.0`), set `1.0` for Kimi 2.5 |
| `USE_AGENT_MODE` | `false` | Enable SQL Agent mode |
| `AGENT_MAX_ITERATIONS` | `15` | Max SQL Agent iterations |
| `AGENT_TIMEOUT_SECONDS` | `240` | Total wall-clock timeout for one SQL Agent execution |
| `QUERY_TIMEOUT_SECONDS` | `300` | End-to-end query timeout including planning, retrieval, and SQL Agent |
| `MAX_SQL_RETRIES` | `3` | SQL generation retries |
| `LLM_PROVIDER` | `openai` | Display only; provider is auto-inferred by model+key |
| `MCP_DBHUB_CONFIG` | empty | DBHub MCP config path (not referenced in code yet) |

Provider priority: Google > Anthropic > OpenAI (requires both model and API key).

---

## 11) Code Context (DDD Retrieval)

| Variable | Default | Description |
| --- | --- | --- |
| `CODE_CONTEXT_ENABLED` | `false` | Enable code context |
| `CODE_CONTEXT_SEARCH_TOP_K` | `5` | Code chunks to retrieve |
| `CODE_CONTEXT_SCORE_THRESHOLD` | `0.3` | Minimum relevance threshold |
| `CODE_CONTEXT_MAX_SNIPPETS` | `3` | Max code snippets in prompt |

Code-context collection prefixes are derived from `PROJECT_NAMESPACE`. Cache directory
(`.code_context_cache`) and supported languages are fixed in code.

---

## 12) Langfuse Observability

| Variable | Default | Description |
| --- | --- | --- |
| `LANGFUSE_ENABLED` | `false` | Enable Langfuse |
| `LANGFUSE_PUBLIC_KEY` | empty | Public key |
| `LANGFUSE_SECRET_KEY` | empty | Secret key |
| `LANGFUSE_BASE_URL` | `https://cloud.langfuse.com` | Base URL (Langfuse SDK standard) |
| `LANGFUSE_HOST` | `https://cloud.langfuse.com` | Legacy alias, still supported for compatibility |

---

## 13) Checkpointer (LangGraph State)

| Variable | Default | Description |
| --- | --- | --- |
| `CHECKPOINTER_BACKEND` | `memory` | `memory` / `postgres` |

PostgreSQL checkpointer mode uses `POSTGRES_URI`. Pool sizes are fixed in code (min 2, max 20).

---

## 14) Session Persistence (PostgreSQL Only)

| Variable | Default | Description |
| --- | --- | --- |
| `SESSION_BACKEND` | `postgres` | Fixed to `postgres` |

Session persistence uses `POSTGRES_URI`.

---

## 15) Few-shot Retrieval

| Variable | Default | Description |
| --- | --- | --- |
| `FEW_SHOT_ENABLED` | `false` | Enable few-shot examples |
| `FEW_SHOT_MAX_EXAMPLES` | `3` | Max examples |
| `FEW_SHOT_MIN_SIMILARITY` | `0.6` | Minimum similarity |

Few-shot collection name is fixed as `few_shot_examples` and prefixed by
`PROJECT_NAMESPACE`.

---

## 16) Web Frontend (Vite)

| Variable | Default | Description |
| --- | --- | --- |
| `VITE_API_BASE_URL` | `/api/v1` | Frontend API base path |

---

## 17) Test-only Variables

These are read via `dotenv` in tests and are not part of the main settings model:

- `LLM_SQL_MODEL` (tests only)
- `NEO4J_URI` / `NEO4J_USER` / `NEO4J_PASSWORD`
- `MILVUS_URI` / `PROJECT_NAMESPACE`

---

## 18) Minimal Example

```ini
# .env
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=your_neo4j_password
PROJECT_NAMESPACE=default
POSTGRES_URI=postgresql://postgres:password@localhost:5432/easysql
MILVUS_URI=http://localhost:19530
EMBEDDING_PROVIDER=local
DB_HIS_TYPE=mysql
DB_HIS_HOST=localhost
DB_HIS_PORT=3306
DB_HIS_USER=root
DB_HIS_PASSWORD=your_mysql_password
DB_HIS_DATABASE=his_db
OPENAI_API_KEY=your_openai_api_key
OPENAI_LLM_MODEL=gpt-4o
```

---

If you add new settings, update `easysql/config.py`, `.env.example`, and this document.
