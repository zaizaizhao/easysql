# EasySQL Review Summary

## Executive Summary

Five review lanes were completed:

- [2026-04-13-backend-architecture-review.md](./2026-04-13-backend-architecture-review.md)
- [2026-04-13-langgraph-workflow-review.md](./2026-04-13-langgraph-workflow-review.md)
- [2026-04-13-rag-and-storage-review.md](./2026-04-13-rag-and-storage-review.md)
- [2026-04-13-config-and-runtime-review.md](./2026-04-13-config-and-runtime-review.md)
- [2026-04-13-infra-observability-review.md](./2026-04-13-infra-observability-review.md)

The most important result is that EasySQL’s current risks are not isolated to one subsystem. Multiple lanes independently point to the same pattern: the codebase has reasonable high-level structure, but too much runtime truth is implicit. Configuration authority, graph state, service ownership, health signals, and retrieval contracts all rely on hidden conventions, process-local caches, or partial projections rather than one explicit operational model.

Using the fixed scoring rule from the execution plan, the selected deep-dive topics are:

- [2026-04-13-config-and-runtime-deep-dive.md](./2026-04-13-config-and-runtime-deep-dive.md)
- [2026-04-13-backend-architecture-deep-dive.md](./2026-04-13-backend-architecture-deep-dive.md)
- [2026-04-13-langgraph-workflow-deep-dive.md](./2026-04-13-langgraph-workflow-deep-dive.md)

These three topics were selected because they carry the highest combined score across correctness risk, architecture leverage, delivery drag, and cross-cutting impact, and third place remains more than one point ahead of fourth place.

## Ranking Matrix

| Lane | Correctness Risk | Architecture Leverage | Delivery Drag | Cross-Cutting Impact | Total | Why |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| [2026-04-13-config-and-runtime-review.md](./2026-04-13-config-and-runtime-review.md) | 5 | 5 | 5 | 5 | 20 | Competing config authorities and incomplete invalidation semantics can silently desynchronize runtime behavior across API, graph, and operator expectations. |
| [2026-04-13-backend-architecture-review.md](./2026-04-13-backend-architecture-review.md) | 4 | 5 | 5 | 5 | 19 | Global service ownership and the oversized `QueryService` shape make backend evolution slower and less predictable across nearly every API feature. |
| [2026-04-13-langgraph-workflow-review.md](./2026-04-13-langgraph-workflow-review.md) | 5 | 5 | 4 | 5 | 19 | Dual-state persistence, mixed execution lanes, and opaque retry semantics create correctness and replay risks in the project’s core Text2SQL path. |
| [2026-04-13-rag-and-storage-review.md](./2026-04-13-rag-and-storage-review.md) | 5 | 4 | 4 | 4 | 17 | Retrieval correctness is exposed to DB-scoping drift and contract leakage, but the blast radius is somewhat narrower than config and workflow authority issues. |
| [2026-04-13-infra-observability-review.md](./2026-04-13-infra-observability-review.md) | 4 | 4 | 3 | 4 | 15 | Docs, logging, and readiness are weaker than the runtime contract, but most of the fixes are clarifying and hardening work rather than deep architectural surgery. |

## Cross-Cutting Themes

1. **Runtime truth is too implicit**
   Multiple lanes found the same systemic issue: the codebase often has the right conceptual layers, but runtime truth lives in process-local caches, module-global state, fallback projections, or undocumented precedence rules. This appears in config authority, LangGraph persistence, backend service ownership, and health semantics.

2. **The project is in partial-migration mode across several axes**
   The codebase is not chaotic; it is transitional. The agent path coexists with the legacy SQL loop, persisted config coexists with env-first settings, and service observability coexists with LLM-only tracing. This is why many issues look like “almost correct” systems rather than outright missing systems.

3. **Operator-facing contracts lag behind implementation reality**
   Docs, health endpoints, editable config, and local startup guidance under-describe important runtime dependencies or overstate readiness. This increases support and debugging cost even when the code itself is working as designed.

4. **The highest-value fixes are boundary fixes, not feature rewrites**
   The most leveraged changes are explicit ownership, explicit precedence, explicit persistence authority, and explicit retriever contracts. None of the top findings require a product rewrite; they require making existing behavior legible and reliable.

## Short-Term Roadmap

1. Fix the highest-confidence correctness and operability gaps first:
   make health and readiness honest,
   fix stale startup docs,
   add tests for config precedence, graph resume, and cross-database retrieval isolation.

2. Remove no-op or ambiguous behavior on hot paths:
   clarify retry semantics,
   add a progress guard to the legacy SQL loop,
   and audit which live config changes must rebuild the compiled graph.

3. Make runtime control explicit for operators:
   document real config precedence,
   document session-store and checkpointer fallback behavior,
   and clearly separate compose-provisioned infra from required external dependencies.

## Medium-Term Roadmap

1. Consolidate configuration authority:
   one authoritative settings boundary,
   explicit persisted-override semantics,
   and refreshable runtime components with deterministic invalidation behavior.

2. Consolidate backend ownership:
   move long-lived runtime resources into app-scoped ownership,
   split `QueryService`,
   and reduce reliance on module-global service locator patterns.

3. Strengthen retrieval contracts:
   make `db_name` first-class in Milvus schema retrieval,
   replace mutable filter context with typed candidates,
   and bring code-context retrieval into the same prompt-artifact system as schema and few-shot context.

4. Strengthen graph persistence authority:
   make checkpoint state the default replay substrate,
   narrow service-layer fallback state,
   and decide whether legacy mode remains a supported lane.

## Later Bets

1. Move the SQL agent toward graph-visible subgraph steps if deterministic replay, richer auditability, or tool-step analytics become strategically important.

2. Promote observability from “LLM tracing exists” to full service telemetry with request-level traces, dependency spans, and exportable metrics.

3. Decide whether persisted config should remain a tuning surface or evolve into a real runtime control plane. That decision should come only after precedence and ownership are already explicit.

## Suggested Execution Order

Deep-dive selection order:

1. [2026-04-13-config-and-runtime-deep-dive.md](./2026-04-13-config-and-runtime-deep-dive.md)
2. [2026-04-13-backend-architecture-deep-dive.md](./2026-04-13-backend-architecture-deep-dive.md)
3. [2026-04-13-langgraph-workflow-deep-dive.md](./2026-04-13-langgraph-workflow-deep-dive.md)

Suggested implementation sequencing after this review:

1. Start with config and runtime authority.
   This unlocks more reliable behavior for graph rebuilds, operator understanding, and later backend cleanup.

2. Then fix backend ownership.
   App-scoped service ownership and `QueryService` decomposition reduce the blast radius of later graph and persistence changes.

3. Then harden LangGraph persistence and lane boundaries.
   Once config and ownership are explicit, graph-state authority and branch correctness can be simplified without fighting hidden service behavior.

4. In parallel or immediately after, fix the top retrieval correctness issue:
   Milvus `db_name` scoping for schema and column retrieval.

5. Fold infra and observability hardening through the above work instead of treating it as a separate rewrite.
   Honest readiness checks, API logging bootstrap, and lifecycle tests should accompany each architectural clarification step.

## Open Questions

- Should environment variables remain the highest-precedence emergency override above persisted DB config, or should persisted config become authoritative for selected categories?
- Is legacy SQL mode still a supported production path, or only a migration safety net?
- Are Milvus collection prefixes guaranteed to be single-database in production?
- Is branch correctness across restart a hard requirement, which would effectively make a Postgres-backed checkpointer part of the real runtime contract?
- Should session store and checkpointer settings stay env-only operational config, or eventually move into the API control plane?
