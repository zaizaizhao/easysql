# LangGraph Workflow Deep Dive

## Problem Statement

EasySQL already relies on LangGraph for orchestration, checkpointing, and branch-aware query execution, but the workflow still behaves like a partially migrated system. It uses checkpointed graph state and `thread_id` correctly at the service boundary, while simultaneously keeping a sanitized service-layer shadow state and a large opaque `SqlAgentNode` loop. This reduces branch clarity, replay fidelity, and confidence in retry behavior.

## Current Architecture And Failure Surfaces

The key failure surfaces are:

- one oversized `EasySQLState` contract representing both legacy and agent execution modes ([easysql/llm/state.py](../easysql/llm/state.py):83)
- duplicate or overlapping state such as `context_output` and `cached_context` ([easysql/llm/nodes/build_context.py](../easysql/llm/nodes/build_context.py):116)
- a compiled graph with two different execution models behind one surrounding service surface ([easysql/llm/agent.py](../easysql/llm/agent.py):251)
- a sanitized `session.state` shadow model used as fallback when checkpoint state is not enough ([easysql_api/services/query_service.py](../easysql_api/services/query_service.py):849, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):955)
- retry semantics that mean different things depending on whether the system is in legacy mode or agent mode ([easysql/llm/nodes/generate_sql.py](../easysql/llm/nodes/generate_sql.py):109, [easysql/llm/nodes/sql_agent.py](../easysql/llm/nodes/sql_agent.py):320)

## Root Causes

The root cause is partial migration from the legacy SQL loop to the agent path. The team adopted LangGraph as the outer orchestration shell and added checkpoint-aware service behavior, but kept the most stateful reasoning logic in bespoke forms:

- a custom service-layer state projection
- a monolithic internal ReAct loop inside `SqlAgentNode`
- legacy and agent execution lanes sharing one broad state schema

This was a reasonable transition strategy, but it leaves ambiguous boundaries between “graph state,” “service state,” and “UI state.”

## Strong Reference Patterns

The stronger LangGraph-native pattern would trust checkpointed graph state as the replay substrate, keep state semantics narrower and more typed by workflow lane, and expose more internal reasoning steps as graph-visible nodes or subgraphs. That does not require abandoning custom streaming or provider-specific handling, but it does mean the system should lean harder on graph-native visibility rather than hiding core reasoning inside one node and one service-layer shadow projection.

## Target Direction

The target direction should be:

- checkpointed graph state becomes the authoritative source for resume and branching
- `session.state` becomes a projection for UI, inspection, or reporting rather than an execution fallback
- retry semantics are made explicit and mode-aware
- the long-lived SQL-agent path moves toward graph-visible stages or at least emits structured per-iteration artifacts into persisted state
- legacy mode is either hardened with strict guards or intentionally deprecated

## Phased Optimization Plan

Phase 1:

- add service-boundary tests for interrupt/resume, branch creation, and restart-sensitive behavior
- add a progress guard to the legacy loop so it cannot cycle through no-op repair behavior
- clarify retry semantics in code and state naming

Phase 2:

- remove redundant state fields and separate lane-specific state concerns
- narrow what `session.state` is allowed to represent

Phase 3:

- make checkpoint state the authoritative branch and replay substrate
- reduce or eliminate fallback execution behavior from sanitized shadow state

Phase 4:

- refactor `SqlAgentNode` into graph-visible stages or a dedicated subgraph if deterministic replay and deeper debugging become strategic requirements

## Migration Risks And Decision Constraints

The biggest migration constraint is compatibility with current query-session behavior. The frontend and API already rely on specific stream events, follow-up behavior, and branch semantics. Any refactor toward graph-visible steps has to preserve those transport contracts or introduce a compatibility layer.

There is also a persistence constraint. If the checkpointer remains `MemorySaver()` in some deployments, then “checkpoint as authority” only holds within one process lifetime. The project needs to decide whether branch correctness across restarts is a hard requirement before fully optimizing around that model.
