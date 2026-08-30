# EasySQL read-only agent tool reference

The FastAPI server must be running. Override the default endpoint when necessary:

```bash
export EASYSQL_AGENT_TOOLS_URL="http://127.0.0.1:8000/api/v1"
```

Run the client from the skill directory:

```bash
python scripts/agent_tools.py databases

python scripts/agent_tools.py search-tables \
  --db emr_demo \
  --query "放射治疗转诊记录和转诊时间" \
  --top-k 5

python scripts/agent_tools.py search-columns \
  --db emr_demo \
  --query "跨系统患者统一标识" \
  --table patient \
  --table service_request

python scripts/agent_tools.py describe-tables \
  --db emr_demo \
  --table patient \
  --table service_request

python scripts/agent_tools.py expand-tables \
  --db rvs_demo \
  --table rt_plan \
  --table rt_patient \
  --max-depth 1

python scripts/agent_tools.py find-join-paths \
  --db rvs_demo \
  --table rt_plan \
  --table rt_patient \
  --max-hops 5

python scripts/agent_tools.py check-sql \
  --db emr_demo \
  --sql-file /absolute/path/to/candidate.sql
```

For a federated SQL safety check, `--db` is the primary database and each selected
remote database is passed with `--database`:

```bash
python scripts/agent_tools.py check-sql \
  --db emr_demo \
  --database pms_demo \
  --database rvs_demo \
  --sql-file /absolute/path/to/candidate.sql
```

## Endpoint map

| Client command | Method and path | Backend capability |
|---|---|---|
| `databases` | `GET /agent-tools/databases` | Credential-free configured scope |
| `search-tables` | `POST /agent-tools/search-tables` | Milvus table search |
| `search-columns` | `POST /agent-tools/search-columns` | Milvus column search |
| `describe-tables` | `POST /agent-tools/table-schema` | Neo4j table columns and key flags |
| `expand-tables` | `POST /agent-tools/expand-tables` | Neo4j FK-neighbor expansion |
| `find-join-paths` | `POST /agent-tools/join-paths` | Neo4j directional FK edges |
| `check-sql` | `POST /execute/check` | Existing non-executing SQL classification |

All paths are relative to the configured `/api/v1` base URL. Tool responses include
`elapsed_ms` except for the static database scope response.

`404 DATABASE_NOT_CONFIGURED` means the logical database is outside the configured
scope. `422` means the request exceeded a budget or contained an invalid identifier.
`503 RETRIEVAL_BACKEND_UNAVAILABLE` means Milvus or Neo4j could not answer; do not
invent a fallback schema.

The SQL check is conservative workflow guidance, not database-plan validation. It
does not execute SQL and does not verify that referenced tables or columns exist.
