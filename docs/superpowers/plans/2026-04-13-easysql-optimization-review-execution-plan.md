# EasySQL Optimization Review Execution Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Produce five backend-focused review documents, select the two or three highest-leverage topics for deep dives, and publish one evidence-backed summary that can drive later optimization work.

**Architecture:** Run the review in two stages. First, create all review artifacts with a shared structure and fill one direction document per lane: backend architecture, LangGraph workflow, RAG and storage, config and runtime, and infrastructure and observability. Second, rank the findings, create deep-dive documents for the top two or three lanes, and finish with one summary document that prioritizes the work and explains sequencing constraints.

**Tech Stack:** Python 3.10, FastAPI, LangGraph, Pydantic Settings, SQLAlchemy, Neo4j, Milvus, Langfuse, Markdown, git

---

## File Structure

### New Review Artifacts

- `docs/review/2026-04-13-backend-architecture-review.md`
- `docs/review/2026-04-13-langgraph-workflow-review.md`
- `docs/review/2026-04-13-rag-and-storage-review.md`
- `docs/review/2026-04-13-config-and-runtime-review.md`
- `docs/review/2026-04-13-infra-observability-review.md`
- `docs/review/2026-04-13-review-summary.md`

### Possible Deep-Dive Artifacts

- `docs/review/2026-04-13-backend-architecture-deep-dive.md`
- `docs/review/2026-04-13-langgraph-workflow-deep-dive.md`
- `docs/review/2026-04-13-rag-and-storage-deep-dive.md`
- `docs/review/2026-04-13-config-and-runtime-deep-dive.md`
- `docs/review/2026-04-13-infra-observability-deep-dive.md`

### Source Files To Read During The Review

- `README.md`
- `docs/ENVIRONMENT.md`
- `docker-compose.yml`
- `easysql/main.py`
- `easysql/pipeline/schema_pipeline.py`
- `easysql/config.py`
- `easysql/llm/agent.py`
- `easysql/llm/state.py`
- `easysql/llm/nodes/*.py`
- `easysql/llm/agents/sql_agent.py`
- `easysql/retrieval/*.py`
- `easysql/context/*.py`
- `easysql/context/sections/*.py`
- `easysql/readers/*.py`
- `easysql/writers/*.py`
- `easysql/repositories/*.py`
- `easysql/code_context/**/*.py`
- `easysql/utils/logger.py`
- `easysql_api/app.py`
- `easysql_api/deps.py`
- `easysql_api/routers/*.py`
- `easysql_api/services/*.py`
- `easysql_api/infrastructure/**/*.py`
- `easysql_api/domain/**/*.py`
- `tests/test_query_service_graph_pinning.py`
- `tests/test_sql_agent_stream.py`
- `tests/test_schema_retrieval_service.py`
- `tests/test_filter_chain.py`
- `tests/test_milvus_reader_filters.py`
- `tests/test_retrieval_runtime.py`
- `tests/test_config_schema.py`
- `tests/test_config_service.py`
- `tests/test_langfuse_config.py`

### Review Rules

- Keep this execution read-only with respect to product code. Only create review artifacts under `docs/review/`.
- Every review document must cite concrete EasySQL code paths by relative path.
- Prefer official documentation and primary sources when discussing framework or infrastructure best practices.
- Use one commit per completed task so findings remain reviewable and reversible.

### Shared Review Outline

Every direction document must contain these sections in this order:

1. `## Scope And Thesis`
2. `## Current Implementation In EasySQL`
3. `## Comparison With Strong Reference Patterns`
4. `## Review Findings`
5. `## Optimization Directions`
6. `## Why These Changes Are Justified`
7. `## Suggested Priority And Follow-up Questions`

Every deep-dive document must contain these sections in this order:

1. `## Problem Statement`
2. `## Current Architecture And Failure Surfaces`
3. `## Root Causes`
4. `## Strong Reference Patterns`
5. `## Target Direction`
6. `## Phased Optimization Plan`
7. `## Migration Risks And Decision Constraints`

The summary document must contain these sections in this order:

1. `## Executive Summary`
2. `## Ranking Matrix`
3. `## Cross-Cutting Themes`
4. `## Short-Term Roadmap`
5. `## Medium-Term Roadmap`
6. `## Later Bets`
7. `## Suggested Execution Order`
8. `## Open Questions`

### Deep-Dive Selection Rule

Score each of the five lane documents from 1 to 5 on these four axes:

- correctness risk
- architecture leverage
- delivery drag
- cross-cutting impact

Pick the top three topics by total score unless third place is only one point ahead of fourth place or less. In that case, pick only the top two topics to keep the deep dives sharper.

## Task 1: Create The Review Workspace And Skeleton Artifacts

**Files:**
- Create: `docs/review/2026-04-13-backend-architecture-review.md`
- Create: `docs/review/2026-04-13-langgraph-workflow-review.md`
- Create: `docs/review/2026-04-13-rag-and-storage-review.md`
- Create: `docs/review/2026-04-13-config-and-runtime-review.md`
- Create: `docs/review/2026-04-13-infra-observability-review.md`
- Create: `docs/review/2026-04-13-review-summary.md`
- Test: `docs/review/2026-04-13-backend-architecture-review.md`
- Test: `docs/review/2026-04-13-review-summary.md`

- [ ] **Step 1: Create the review output directory**

Run: `mkdir -p docs/review`
Expected: `docs/review` exists and is ready for review artifacts.

- [ ] **Step 2: Write the initial skeletons for all five direction docs and the summary doc**

Use one patch that creates the six files with the exact headings below.

```md
# Backend Architecture Review
## Scope And Thesis
## Current Implementation In EasySQL
## Comparison With Strong Reference Patterns
## Review Findings
## Optimization Directions
## Why These Changes Are Justified
## Suggested Priority And Follow-up Questions

# LangGraph Workflow Review
## Scope And Thesis
## Current Implementation In EasySQL
## Comparison With Strong Reference Patterns
## Review Findings
## Optimization Directions
## Why These Changes Are Justified
## Suggested Priority And Follow-up Questions

# RAG And Storage Review
## Scope And Thesis
## Current Implementation In EasySQL
## Comparison With Strong Reference Patterns
## Review Findings
## Optimization Directions
## Why These Changes Are Justified
## Suggested Priority And Follow-up Questions

# Config And Runtime Review
## Scope And Thesis
## Current Implementation In EasySQL
## Comparison With Strong Reference Patterns
## Review Findings
## Optimization Directions
## Why These Changes Are Justified
## Suggested Priority And Follow-up Questions

# Infrastructure And Observability Review
## Scope And Thesis
## Current Implementation In EasySQL
## Comparison With Strong Reference Patterns
## Review Findings
## Optimization Directions
## Why These Changes Are Justified
## Suggested Priority And Follow-up Questions

# EasySQL Review Summary
## Executive Summary
## Ranking Matrix
## Cross-Cutting Themes
## Short-Term Roadmap
## Medium-Term Roadmap
## Later Bets
## Suggested Execution Order
## Open Questions
```

- [ ] **Step 3: Verify the skeletons exist and contain the required headings**

Run: `rg -n "^#|^##" docs/review/2026-04-13-*.md`
Expected: all six files appear and each file contains the required heading sequence.

- [ ] **Step 4: Commit the scaffolded review workspace**

```bash
git add docs/review/2026-04-13-backend-architecture-review.md docs/review/2026-04-13-langgraph-workflow-review.md docs/review/2026-04-13-rag-and-storage-review.md docs/review/2026-04-13-config-and-runtime-review.md docs/review/2026-04-13-infra-observability-review.md docs/review/2026-04-13-review-summary.md
git commit -F - <<'EOF'
Establish a review workspace before architecture findings are collected

This creates the review artifact set and locks a shared structure so each lane
can be filled in with comparable evidence and later synthesized without format
drift.

Constraint: Review execution is documentation-only and must not modify product code
Rejected: Start writing findings directly into one file | weak lane ownership and poor synthesis
Confidence: high
Scope-risk: narrow
Directive: Keep every lane document aligned to the shared heading order
Tested: Heading presence across the six seeded review files
Not-tested: Any lane findings or deep-dive content
EOF
```

## Task 2: Write The Backend Architecture Review

**Files:**
- Modify: `docs/review/2026-04-13-backend-architecture-review.md`
- Read: `README.md`
- Read: `easysql/main.py`
- Read: `easysql/pipeline/schema_pipeline.py`
- Read: `easysql_api/app.py`
- Read: `easysql_api/deps.py`
- Read: `easysql_api/services/query_service.py`
- Read: `easysql_api/services/config_service.py`
- Read: `easysql_api/infrastructure/db.py`
- Read: `easysql_api/domain/repositories/session_repository.py`
- Read: `easysql_api/infrastructure/persistence/session_repository.py`
- Test: `docs/review/2026-04-13-backend-architecture-review.md`

- [ ] **Step 1: Inspect the backend layering and startup wiring**

Run: `sed -n '1,220p' easysql/main.py`
Run: `sed -n '1,260p' easysql/pipeline/schema_pipeline.py`
Run: `sed -n '1,240p' easysql_api/app.py`
Run: `sed -n '1,240p' easysql_api/deps.py`
Run: `sed -n '1,260p' easysql_api/services/query_service.py`
Run: `sed -n '1,240p' easysql_api/services/config_service.py`
Run: `sed -n '1,240p' easysql_api/infrastructure/db.py`
Expected: you can explain the current entrypoints, dependency wiring, service boundaries, and persistence seams without guessing from README text alone.

- [ ] **Step 2: Review stronger reference patterns for FastAPI application structure**

Read and take notes from these sources:

- `https://fastapi.tiangolo.com/tutorial/bigger-applications/`
- `https://fastapi.tiangolo.com/advanced/events/`
- `https://github.com/tiangolo/full-stack-fastapi-template`

Expected: you have enough reference material to compare EasySQL's layering and startup composition against stronger patterns.

- [ ] **Step 3: Fill the backend review document with concrete architecture analysis**

Write the document so that:

- `## Scope And Thesis` names the Python backend surfaces under review and the main architectural claim
- `## Current Implementation In EasySQL` explicitly references `easysql/main.py`, `easysql/pipeline/schema_pipeline.py`, `easysql_api/app.py`, `easysql_api/services/query_service.py`, and `easysql_api/infrastructure/db.py`
- `## Comparison With Strong Reference Patterns` compares EasySQL against the FastAPI docs and one concrete reference project
- `## Review Findings` lists at least three backend-architecture findings
- `## Optimization Directions` proposes staged improvements instead of one large rewrite

- [ ] **Step 4: Verify the backend review contains code-path evidence and comparison material**

Run: `rg -n "easysql/main.py|easysql/pipeline/schema_pipeline.py|easysql_api/app.py|easysql_api/services/query_service.py|easysql_api/infrastructure/db.py" docs/review/2026-04-13-backend-architecture-review.md`
Run: `rg -n "fastapi.tiangolo.com|full-stack-fastapi-template" docs/review/2026-04-13-backend-architecture-review.md`
Expected: the review cites the required EasySQL files and at least one strong external comparison source.

- [ ] **Step 5: Commit the backend architecture review**

```bash
git add docs/review/2026-04-13-backend-architecture-review.md
git commit -F - <<'EOF'
Capture the backend architecture before proposing structural changes

This review records the current Python backend boundaries, startup wiring, and
service-to-persistence seams so later optimization work can be justified with
code evidence instead of intuition.

Constraint: Review must stay read-only and backend-focused
Rejected: Infer architecture quality from the README alone | the code paths are the source of truth
Confidence: medium
Scope-risk: narrow
Directive: Keep frontend concerns out unless they change backend contracts
Tested: Required sections, EasySQL code references, and comparison-source references in the review doc
Not-tested: Any backend refactor or runtime behavior
EOF
```

## Task 3: Write The LangGraph Workflow Review

**Files:**
- Modify: `docs/review/2026-04-13-langgraph-workflow-review.md`
- Read: `easysql/llm/agent.py`
- Read: `easysql/llm/state.py`
- Read: `easysql/llm/nodes/analyze.py`
- Read: `easysql/llm/nodes/build_context.py`
- Read: `easysql/llm/nodes/generate_sql.py`
- Read: `easysql/llm/nodes/repair_sql.py`
- Read: `easysql/llm/nodes/retrieve.py`
- Read: `easysql/llm/nodes/sql_agent.py`
- Read: `easysql/llm/nodes/validate_sql.py`
- Read: `easysql/llm/agents/sql_agent.py`
- Read: `tests/test_query_service_graph_pinning.py`
- Read: `tests/test_sql_agent_stream.py`
- Test: `docs/review/2026-04-13-langgraph-workflow-review.md`

- [ ] **Step 1: Inspect graph assembly, state transitions, and the agent-mode split**

Run: `sed -n '1,320p' easysql/llm/agent.py`
Run: `sed -n '1,260p' easysql/llm/state.py`
Run: `sed -n '1,240p' easysql/llm/nodes/sql_agent.py`
Run: `sed -n '1,260p' easysql/llm/agents/sql_agent.py`
Run: `sed -n '1,220p' tests/test_query_service_graph_pinning.py`
Run: `sed -n '1,220p' tests/test_sql_agent_stream.py`
Expected: you can explain graph routing, checkpointer usage, mode branching, and how the tests pin behavior.

- [ ] **Step 2: Review strong reference patterns for LangGraph workflows and persistence**

Read and take notes from these sources:

- `https://langchain-ai.github.io/langgraph/`
- `https://langchain-ai.github.io/langgraph/concepts/low_level/`
- `https://langchain-ai.github.io/langgraph/concepts/persistence/`
- `https://github.com/langchain-ai/langgraph/tree/main/examples`

Expected: you can compare EasySQL's current graph composition against official LangGraph state, persistence, and example patterns.

- [ ] **Step 3: Fill the LangGraph workflow review with concrete findings**

Write the document so that:

- `## Current Implementation In EasySQL` references `easysql/llm/agent.py`, `easysql/llm/state.py`, and at least three node or agent files
- `## Comparison With Strong Reference Patterns` explains where EasySQL aligns with or diverges from official LangGraph guidance
- `## Review Findings` discusses state-shape clarity, retry behavior, mode coexistence, and debuggability
- `## Optimization Directions` describes changes that improve observability and extension without forcing a rewrite

- [ ] **Step 4: Verify the LangGraph review cites both local code and external references**

Run: `rg -n "easysql/llm/agent.py|easysql/llm/state.py|easysql/llm/nodes|easysql/llm/agents/sql_agent.py" docs/review/2026-04-13-langgraph-workflow-review.md`
Run: `rg -n "langgraph" docs/review/2026-04-13-langgraph-workflow-review.md`
Expected: the review contains local code citations and explicit LangGraph reference material.

- [ ] **Step 5: Commit the LangGraph workflow review**

```bash
git add docs/review/2026-04-13-langgraph-workflow-review.md
git commit -F - <<'EOF'
Document how the current LangGraph workflow constrains future evolution

This review captures the present graph layout, state design, and agent-mode split
so workflow changes can be prioritized around correctness and debuggability.

Constraint: The review must compare against official LangGraph guidance, not generic agent lore
Rejected: Treat the graph as an opaque black box | hides state and retry failure surfaces
Confidence: medium
Scope-risk: narrow
Directive: Keep the review focused on graph structure, state, and persistence behavior
Tested: Required sections, local LangGraph file references, and external LangGraph citations in the review doc
Not-tested: Any workflow rewrite or runtime trace capture
EOF
```

## Task 4: Write The RAG And Storage Review

**Files:**
- Modify: `docs/review/2026-04-13-rag-and-storage-review.md`
- Read: `easysql/retrieval/schema_retrieval.py`
- Read: `easysql/retrieval/semantic_filter.py`
- Read: `easysql/retrieval/llm_filter.py`
- Read: `easysql/retrieval/bridge_filter.py`
- Read: `easysql/readers/neo4j_reader.py`
- Read: `easysql/readers/milvus_reader.py`
- Read: `easysql/readers/few_shot_reader.py`
- Read: `easysql/writers/neo4j_writer.py`
- Read: `easysql/writers/milvus_writer.py`
- Read: `easysql/writers/few_shot_writer.py`
- Read: `easysql/repositories/neo4j_repository.py`
- Read: `easysql/repositories/milvus_repository.py`
- Read: `easysql/context/builder.py`
- Read: `easysql/context/sections/schema_section.py`
- Read: `easysql/context/sections/join_path_section.py`
- Read: `easysql/context/sections/few_shot_section.py`
- Read: `easysql/code_context/pipeline/sync_pipeline.py`
- Read: `easysql/code_context/retrieval/code_retrieval.py`
- Read: `tests/test_schema_retrieval_service.py`
- Read: `tests/test_filter_chain.py`
- Read: `tests/test_milvus_reader_filters.py`
- Read: `tests/test_retrieval_runtime.py`
- Test: `docs/review/2026-04-13-rag-and-storage-review.md`

- [ ] **Step 1: Inspect the retrieval stack and storage abstractions**

Run: `sed -n '1,260p' easysql/retrieval/schema_retrieval.py`
Run: `sed -n '1,220p' easysql/retrieval/semantic_filter.py`
Run: `sed -n '1,220p' easysql/retrieval/llm_filter.py`
Run: `sed -n '1,220p' easysql/retrieval/bridge_filter.py`
Run: `sed -n '1,240p' easysql/context/builder.py`
Run: `sed -n '1,220p' easysql/code_context/pipeline/sync_pipeline.py`
Expected: you can explain how semantic retrieval, graph retrieval, few-shot retrieval, and code context retrieval are assembled today.

- [ ] **Step 2: Review strong reference patterns for graph-plus-vector retrieval**

Read and take notes from these sources:

- `https://milvus.io/docs`
- `https://neo4j.com/docs/`
- `https://github.com/neo4j/neo4j-graphrag-python`
- `https://docs.llamaindex.ai/en/stable/`

Expected: you can compare EasySQL's retrieval composition to current graph-RAG and hybrid-retrieval patterns from official or strong reference sources.

- [ ] **Step 3: Fill the RAG and storage review with concrete findings**

Write the document so that:

- `## Current Implementation In EasySQL` references at least six local files across retrieval, readers or writers, context assembly, and code-context retrieval
- `## Comparison With Strong Reference Patterns` discusses storage abstraction boundaries and retrieval orchestration choices
- `## Review Findings` identifies where storage concerns leak across layers or where retrieval contracts are weak
- `## Optimization Directions` proposes improvements that preserve optionality around Neo4j, Milvus, few-shot, and code-context subsystems

- [ ] **Step 4: Verify the RAG review contains broad code coverage and reference material**

Run: `rg -n "easysql/retrieval|easysql/readers|easysql/writers|easysql/context|easysql/code_context" docs/review/2026-04-13-rag-and-storage-review.md`
Run: `rg -n "milvus|neo4j|llamaindex|graphrag" docs/review/2026-04-13-rag-and-storage-review.md`
Expected: the review cites both EasySQL retrieval code and relevant external reference material.

- [ ] **Step 5: Commit the RAG and storage review**

```bash
git add docs/review/2026-04-13-rag-and-storage-review.md
git commit -F - <<'EOF'
Make the retrieval and storage architecture reviewable before optimizing it

This review captures how Neo4j, Milvus, few-shot retrieval, and code-context
logic currently interact so storage boundaries and retrieval contracts can be
improved with evidence.

Constraint: Recommendations must preserve optionality instead of hardcoding one retrieval stack
Rejected: Judge retrieval quality from README positioning alone | the code shows the real coupling points
Confidence: medium
Scope-risk: narrow
Directive: Distinguish storage abstraction problems from ranking-quality problems
Tested: Required sections, retrieval-code references, and external graph or vector reference citations in the review doc
Not-tested: Any retrieval benchmark or production recall measurement
EOF
```

## Task 5: Write The Config And Runtime Review

**Files:**
- Modify: `docs/review/2026-04-13-config-and-runtime-review.md`
- Read: `README.md`
- Read: `docs/ENVIRONMENT.md`
- Read: `easysql/config.py`
- Read: `easysql_api/app.py`
- Read: `easysql_api/deps.py`
- Read: `easysql_api/services/config_service.py`
- Read: `easysql_api/services/config_schema.py`
- Read: `easysql_api/routers/config.py`
- Read: `tests/test_config_schema.py`
- Read: `tests/test_config_service.py`
- Read: `tests/test_langfuse_config.py`
- Test: `docs/review/2026-04-13-config-and-runtime-review.md`

- [ ] **Step 1: Inspect how settings, runtime overrides, and persisted config interact**

Run: `sed -n '1,360p' easysql/config.py`
Run: `sed -n '1,260p' easysql_api/services/config_service.py`
Run: `sed -n '1,260p' easysql_api/services/config_schema.py`
Run: `sed -n '1,240p' easysql_api/routers/config.py`
Run: `sed -n '1,220p' tests/test_config_schema.py`
Run: `sed -n '1,220p' tests/test_config_service.py`
Expected: you can describe the flow from env settings to runtime overrides to persisted API config and explain where configuration truth currently lives.

- [ ] **Step 2: Review strong reference patterns for application settings**

Read and take notes from these sources:

- `https://docs.pydantic.dev/latest/concepts/pydantic_settings/`
- `https://fastapi.tiangolo.com/advanced/settings/`
- `https://12factor.net/config`

Expected: you can compare EasySQL's configuration model against well-established settings and runtime-config patterns.

- [ ] **Step 3: Fill the config and runtime review with concrete findings**

Write the document so that:

- `## Current Implementation In EasySQL` references `easysql/config.py`, `easysql_api/services/config_service.py`, `easysql_api/routers/config.py`, and at least one config-related test file
- `## Comparison With Strong Reference Patterns` explains where EasySQL is stronger or weaker than the Pydantic Settings, FastAPI settings, and 12-factor guidance
- `## Review Findings` addresses config source-of-truth clarity, runtime override safety, and local-versus-deployed operability
- `## Optimization Directions` proposes a staged cleanup that improves coherence without breaking current behavior

- [ ] **Step 4: Verify the config review cites both EasySQL config paths and external guidance**

Run: `rg -n "easysql/config.py|easysql_api/services/config_service.py|easysql_api/routers/config.py|tests/test_config" docs/review/2026-04-13-config-and-runtime-review.md`
Run: `rg -n "pydantic|fastapi|12factor" docs/review/2026-04-13-config-and-runtime-review.md`
Expected: the review includes required local code references and configuration-pattern comparisons.

- [ ] **Step 5: Commit the config and runtime review**

```bash
git add docs/review/2026-04-13-config-and-runtime-review.md
git commit -F - <<'EOF'
Clarify the configuration model before changing runtime behavior

This review records how env settings, runtime overrides, and persisted API
configuration interact so later cleanup can reduce ambiguity without breaking
current entrypoints.

Constraint: The analysis must reflect both CLI and API runtime paths
Rejected: Treat env files as the only source of truth | runtime overrides and persistence already exist
Confidence: medium
Scope-risk: narrow
Directive: Keep the review grounded in current config flows instead of idealized config systems
Tested: Required sections, config-file references, and external settings guidance citations in the review doc
Not-tested: Any config migration or deployment rollout
EOF
```

## Task 6: Write The Infrastructure And Observability Review

**Files:**
- Modify: `docs/review/2026-04-13-infra-observability-review.md`
- Read: `README.md`
- Read: `docs/ENVIRONMENT.md`
- Read: `docker-compose.yml`
- Read: `alembic.ini`
- Read: `alembic/env.py`
- Read: `easysql/main.py`
- Read: `easysql/utils/logger.py`
- Read: `easysql_api/app.py`
- Read: `easysql_api/routers/health.py`
- Read: `easysql_api/infrastructure/db.py`
- Read: `tests/test_langfuse_config.py`
- Test: `docs/review/2026-04-13-infra-observability-review.md`

- [ ] **Step 1: Inspect startup, migration, health, and logging surfaces**

Run: `sed -n '1,220p' docker-compose.yml`
Run: `sed -n '1,220p' alembic.ini`
Run: `sed -n '1,260p' alembic/env.py`
Run: `sed -n '1,220p' easysql/utils/logger.py`
Run: `sed -n '1,240p' easysql_api/app.py`
Run: `sed -n '1,220p' easysql_api/routers/health.py`
Run: `sed -n '1,240p' easysql_api/infrastructure/db.py`
Expected: you can explain what infrastructure the repo starts, what it assumes exists elsewhere, and what can be observed during normal startup and failure.

- [ ] **Step 2: Review strong reference patterns for app lifecycle and observability**

Read and take notes from these sources:

- `https://fastapi.tiangolo.com/advanced/events/`
- `https://fastapi.tiangolo.com/advanced/health-checks/`
- `https://langfuse.com/docs`
- `https://opentelemetry.io/docs/`

Expected: you can compare EasySQL's current lifecycle, health, logging, and tracing story against stronger operational patterns.

- [ ] **Step 3: Fill the infrastructure and observability review with concrete findings**

Write the document so that:

- `## Current Implementation In EasySQL` references `docker-compose.yml`, `easysql_api/app.py`, `easysql_api/routers/health.py`, `easysql/utils/logger.py`, and the Alembic files
- `## Comparison With Strong Reference Patterns` covers startup lifecycle, health signaling, and tracing or logging depth
- `## Review Findings` identifies operational blind spots, setup assumptions, and failure-reporting gaps
- `## Optimization Directions` proposes changes that make the system more diagnosable and deployment-friendly

- [ ] **Step 4: Verify the infrastructure review includes both local and external observability references**

Run: `rg -n "docker-compose.yml|easysql_api/app.py|easysql_api/routers/health.py|easysql/utils/logger.py|alembic" docs/review/2026-04-13-infra-observability-review.md`
Run: `rg -n "fastapi|langfuse|opentelemetry" docs/review/2026-04-13-infra-observability-review.md`
Expected: the review contains the required EasySQL operational surfaces and external observability references.

- [ ] **Step 5: Commit the infrastructure and observability review**

```bash
git add docs/review/2026-04-13-infra-observability-review.md
git commit -F - <<'EOF'
Describe the operational model before tightening infrastructure assumptions

This review records how EasySQL starts, what infrastructure it assumes, and
what observability surfaces exist today so operational improvements can be
prioritized with concrete evidence.

Constraint: The review must separate current capabilities from production-ready aspirations
Rejected: Treat logging and tracing as equivalent | they solve different debugging problems
Confidence: medium
Scope-risk: narrow
Directive: Keep infrastructure findings tied to actual startup and health code paths
Tested: Required sections, operational code references, and external observability citations in the review doc
Not-tested: Any deployment or tracing integration change
EOF
```

## Task 7: Select Deep-Dive Topics And Write The Deep Dives

**Files:**
- Modify: `docs/review/2026-04-13-review-summary.md`
- Create: selected files from the deep-dive artifact set listed in `## File Structure`
- Test: `docs/review/2026-04-13-review-summary.md`

- [ ] **Step 1: Score all five lane documents inside the summary file**

Fill `## Ranking Matrix` in `docs/review/2026-04-13-review-summary.md` with one row per lane and four numeric scores:

- correctness risk
- architecture leverage
- delivery drag
- cross-cutting impact

Also include one sentence per lane that explains the score.

- [ ] **Step 2: Select the deep-dive topics with the fixed scoring rule**

Apply the rule from the header of this plan:

- pick the top three topics by total score
- if third place is only one point ahead of fourth place or less, keep only the top two

Write the selected lane names into `## Executive Summary` and `## Suggested Execution Order` in the summary doc before creating the deep dives.

- [ ] **Step 3: Create the deep-dive files for the selected topics**

Each selected deep-dive file must contain the exact heading order below and must reference the matching lane review plus concrete EasySQL code paths:

```md
# <Topic> Deep Dive
## Problem Statement
## Current Architecture And Failure Surfaces
## Root Causes
## Strong Reference Patterns
## Target Direction
## Phased Optimization Plan
## Migration Risks And Decision Constraints
```

The content must go beyond the lane review by adding root causes, target direction, staged rollout advice, and migration or compatibility risks.

- [ ] **Step 4: Verify the selected deep dives exist and the summary names them explicitly**

Run: `rg -n "backend-architecture|langgraph-workflow|rag-and-storage|config-and-runtime|infra-observability" docs/review/2026-04-13-review-summary.md`
Run: `find docs/review -maxdepth 1 -name '2026-04-13-*-deep-dive.md'`
Expected: the summary names the selected deep-dive topics, and exactly two or three deep-dive files exist.

- [ ] **Step 5: Commit the deep-dive selection and deep-dive docs**

```bash
git add docs/review/2026-04-13-review-summary.md docs/review/2026-04-13-*-deep-dive.md
git commit -F - <<'EOF'
Deepen the highest-leverage review topics before final prioritization

This adds deep-dive analysis only for the lanes that scored highest on risk,
leverage, delivery drag, and cross-cutting impact so the final summary can
recommend concrete next moves instead of generic refactoring.

Constraint: Deep-dive selection must follow the scoring rule rather than preference drift
Rejected: Deep-dive every lane | too shallow for the most important topics
Confidence: medium
Scope-risk: moderate
Directive: Keep each deep dive tied to its lane review and code evidence
Tested: Ranking matrix completed, selected topics named in the summary, and two or three deep-dive files created
Not-tested: Any implementation plan derived from the deep dives
EOF
```

## Task 8: Finish The Summary And Run Final Verification

**Files:**
- Modify: `docs/review/2026-04-13-review-summary.md`
- Test: `docs/review/2026-04-13-backend-architecture-review.md`
- Test: `docs/review/2026-04-13-langgraph-workflow-review.md`
- Test: `docs/review/2026-04-13-rag-and-storage-review.md`
- Test: `docs/review/2026-04-13-config-and-runtime-review.md`
- Test: `docs/review/2026-04-13-infra-observability-review.md`
- Test: `docs/review/2026-04-13-review-summary.md`

- [ ] **Step 1: Finish the summary document**

Fill the remaining sections so the summary includes:

- a concise executive readout
- the ranking matrix with explicit scores and rationale
- cross-cutting themes that appear in multiple lane docs
- short-term, medium-term, and later recommendations
- an execution order that sequences low-risk enablers before broader refactors
- open questions that still need proof before implementation

- [ ] **Step 2: Verify every direction doc follows the shared outline**

Run: `rg -n "^## Scope And Thesis|^## Current Implementation In EasySQL|^## Comparison With Strong Reference Patterns|^## Review Findings|^## Optimization Directions|^## Why These Changes Are Justified|^## Suggested Priority And Follow-up Questions" docs/review/2026-04-13-*-review.md`
Expected: every direction file contains the full heading set.

- [ ] **Step 3: Verify the summary references all five review lanes and the selected deep dives**

Run: `rg -n "backend-architecture-review|langgraph-workflow-review|rag-and-storage-review|config-and-runtime-review|infra-observability-review" docs/review/2026-04-13-review-summary.md`
Run: `rg -n "deep-dive" docs/review/2026-04-13-review-summary.md`
Expected: the summary ties together all lane reviews and the chosen deep dives.

- [ ] **Step 4: Review git status to ensure only review artifacts are included**

Run: `git status --short`
Expected: only the review documents for this execution appear as newly created or modified files.

- [ ] **Step 5: Commit the completed review summary and verification pass**

```bash
git add docs/review/2026-04-13-backend-architecture-review.md docs/review/2026-04-13-langgraph-workflow-review.md docs/review/2026-04-13-rag-and-storage-review.md docs/review/2026-04-13-config-and-runtime-review.md docs/review/2026-04-13-infra-observability-review.md docs/review/2026-04-13-review-summary.md docs/review/2026-04-13-*-deep-dive.md
git commit -F - <<'EOF'
Summarize the architecture review so optimization work can be sequenced

This finalizes the backend-focused review set and adds a prioritized summary so
future implementation work can start from explicit evidence, dependencies, and
tradeoffs instead of unfocused cleanup.

Constraint: The summary must prioritize by leverage and risk, not by document order
Rejected: End with independent lane docs only | no cross-cutting prioritization
Confidence: medium
Scope-risk: moderate
Directive: Use this summary as input to planning, not as permission for blanket refactoring
Tested: Heading verification across lane docs, summary cross-links, and git-status check for review artifacts
Not-tested: Any implementation work based on the recommendations
EOF
```
