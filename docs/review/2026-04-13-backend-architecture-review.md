# Backend Architecture Review

## Scope And Thesis

This review covers the EasySQL backend architecture lane across the CLI and schema pipeline entrypoints, FastAPI application lifecycle, dependency wiring, query and configuration services, and session persistence. The architecture is directionally reasonable at the package level: there is visible separation between routers, services, domain entities, infrastructure persistence, and the standalone schema pipeline. The main structural weakness is not the absence of layers, but the amount of process-global mutable state sitting above those layers. In practice, lifecycle correctness depends on startup order, cache invalidation discipline, and singleton reset behavior, which will make testing, multi-worker deployment, and incremental evolution harder than necessary.

## Current Implementation In EasySQL

The repository exposes two backend modes from the same CLI surface. `easysql/main.py` runs the schema extraction and write pipeline by default through the Typer callback, while `serve` launches the FastAPI app via `uvicorn` ([easysql/main.py](../easysql/main.py):18, [easysql/main.py](../easysql/main.py):27, [easysql/main.py](../easysql/main.py):58, [easysql/main.py](../easysql/main.py):182). That means the repo already contains two different backend runtime styles: a synchronous orchestration flow for schema sync and an asynchronous request-serving API.

The schema path is comparatively clean. `SchemaPipeline` lazily constructs the Neo4j repository, Milvus repository, writers, and embedding service, then runs extract, Neo4j write, and Milvus write phases in order while accumulating typed execution stats ([easysql/pipeline/schema_pipeline.py](../easysql/pipeline/schema_pipeline.py):22, [easysql/pipeline/schema_pipeline.py](../easysql/pipeline/schema_pipeline.py):54, [easysql/pipeline/schema_pipeline.py](../easysql/pipeline/schema_pipeline.py):119). This is a conventional orchestration object with explicit phase boundaries and low hidden state.

The FastAPI side uses `lifespan`, which is the right top-level lifecycle primitive. On startup the app validates session-store prerequisites, initializes the SQLAlchemy engine, creates the session repository, bootstraps persisted runtime overrides, logs effective model settings, and sets up the LangGraph checkpointer when PostgreSQL persistence is enabled ([easysql_api/app.py](../easysql_api/app.py):25, [easysql_api/app.py](../easysql_api/app.py):39, [easysql_api/app.py](../easysql_api/app.py):52, [easysql_api/app.py](../easysql_api/app.py):61). On shutdown it clears dependency globals and disposes engine and checkpointer resources ([easysql_api/app.py](../easysql_api/app.py):67).

The problem is how these resources are shared after startup. Instead of app-scoped state or request-scoped dependency composition, `easysql_api/deps.py` acts as a process-wide service locator. `_session_repository` and `_config_service` are module globals populated during startup, and downstream dependencies read those globals directly ([easysql_api/deps.py](../easysql_api/deps.py):12, [easysql_api/deps.py](../easysql_api/deps.py):20, [easysql_api/deps.py](../easysql_api/deps.py):36, [easysql_api/deps.py](../easysql_api/deps.py):49). The DB infrastructure uses the same pattern: `_engine` and `_sessionmaker` are module globals initialized once and later disposed globally ([easysql_api/infrastructure/db.py](../easysql_api/infrastructure/db.py):10, [easysql_api/infrastructure/db.py](../easysql_api/infrastructure/db.py):24, [easysql_api/infrastructure/db.py](../easysql_api/infrastructure/db.py):39).

`QueryService` is the central orchestration surface for API query execution, and it has accumulated multiple responsibilities. It lazily builds and caches the LangGraph graph, resolves Langfuse callbacks, creates sessions, manages branch and fork behavior, persists turns and messages, translates graph results into transport responses, and sanitizes stored state ([easysql_api/services/query_service.py](../easysql_api/services/query_service.py):24, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):30, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):164, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):540, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):666, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):797, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):902). Architecturally, this is where API orchestration, session lifecycle, persistence coordination, and SSE shaping are collapsed into one service object.

The persistence boundary itself is better designed than the service layer. There is a domain-level `SessionRepository` protocol and a concrete SQLAlchemy implementation, which is a healthy seam ([easysql_api/domain/repositories/session_repository.py](../easysql_api/domain/repositories/session_repository.py):1, [easysql_api/infrastructure/persistence/session_repository.py](../easysql_api/infrastructure/persistence/session_repository.py):26). However, the mapper has to reconstruct message-to-turn linkage heuristically by matching `generated_sql` strings and then falling back to message order, which indicates the storage model does not encode all the relationships the domain now depends on ([easysql_api/infrastructure/persistence/session_repository.py](../easysql_api/infrastructure/persistence/session_repository.py):302, [easysql_api/infrastructure/persistence/session_repository.py](../easysql_api/infrastructure/persistence/session_repository.py):320).

## Comparison With Strong Reference Patterns

EasySQL aligns with FastAPI’s official guidance in a few important ways. The app assembly is thin, routers are registered centrally, and shared startup and shutdown work is managed in `lifespan`, which is the recommended pattern in the FastAPI lifecycle docs. That gives the project a sensible top-level shape rather than hiding boot logic inside ad hoc import side effects.

The main divergence from stronger reference patterns is dependency and resource ownership. FastAPI’s “bigger applications” guidance encourages clear routing and dependency boundaries, and reference projects such as the FastAPI full-stack template tend to keep app assembly thin while exposing request-scoped dependencies from explicit providers instead of mutating module globals. EasySQL currently initializes resources in `lifespan`, but then exports them through global setter/getter functions in `deps.py` and `infrastructure/db.py`. This keeps wiring simple in the short term, but makes runtime behavior implicit: whether a dependency works depends on whether startup ran in the right process and whether every reset hook was executed in the right order.

There is also a contrast between the pipeline side and the API side. `SchemaPipeline` is closer to a strong orchestration pattern: resources are lazy, ownership is local to the object, and the execution phases are explicit. The API runtime takes the opposite direction and centralizes shared state in process-level globals. The inconsistency matters because it suggests the codebase does not have one stable ownership model across backend surfaces.

## Review Findings

1. The highest-leverage architectural issue is the use of process-global mutable state for core backend resources. `lifespan()` populates repository and config service globals, the DB engine and sessionmaker are global singletons, and query execution also depends on global cached graph and callback state. This turns startup order and reset behavior into part of correctness rather than implementation detail.

2. `QueryService` has become a god-service. It mixes graph runtime access, branch semantics, state shaping, persistence coordination, transport-facing streaming, and response sanitization into one class. That is already hard to test in isolation, and it increases the probability that future feature work will keep piling into the same file because it already “owns” everything adjacent to query execution.

3. Runtime configuration and backend orchestration are coupled more tightly than the package layout suggests. Persisted config rows become process-global runtime overrides, caches are invalidated manually, and downstream services implicitly rely on those invalidation hooks to remain coherent. That makes the architecture look cleaner on disk than it is at runtime.

4. The repository abstraction is good, but the persistence model is lagging behind the domain behavior. The SQLAlchemy repository has to infer relationships that should ideally be stored explicitly, especially around message and turn mapping. That is a design smell: once mapping logic becomes heuristic, the infrastructure layer starts carrying hidden product rules.

5. There is still a strong base to work from. The app assembly is thin, routers are separated, the schema pipeline is phase-oriented, and the domain repository seam exists. This is not a “rewrite the backend” situation. It is a “make ownership explicit and reduce hidden coupling” situation.

## Optimization Directions

1. Replace module-global service state with an explicit application container. The simplest path is to attach initialized services to `app.state` during `lifespan`, and have dependencies resolve them from `Request.app.state` rather than `set_*` and `clear_*` helpers. That preserves current layering while removing hidden global ownership.

2. Split `QueryService` into narrower units with clear boundaries:
   one unit for graph runtime orchestration,
   one for session and turn persistence coordination,
   and one for streaming or response translation. The current class has enough behavior to justify that split without inventing extra abstraction for its own sake.

3. Turn runtime config reload into a first-class backend lifecycle concern. Instead of a process-global override dict plus cache-clear conventions, use typed reloadable components with explicit refresh points and clearly documented invariants. This is especially important if the API is ever expected to run with multiple workers.

4. Persist explicit message-to-turn relationships in the session store rather than reconstructing them from `generated_sql` and ordering heuristics. That will simplify the repository implementation and reduce the chance of subtle history bugs as branching and few-shot behavior keep growing.

5. Keep the phase-oriented orchestration style from `SchemaPipeline`, but avoid transplanting it into shared process state. Local ownership plus explicit phase methods is the part worth reusing, not the singleton pattern that appeared on the API side.

## Why These Changes Are Justified

These changes target the real backend risk surface. The repo does not primarily suffer from missing folders or missing abstractions; it suffers from hidden ownership and runtime coupling across layers that otherwise look separated. That is why the most valuable improvements are around explicit service lifetimes, narrower orchestration seams, and persistence models that encode the relationships the product already needs.

The recommendations are also staged rather than rewrite-oriented. The current package layout, router split, and repository protocol already provide usable anchors. Moving services into app-scoped ownership, decomposing `QueryService`, and hardening stored relationships can all happen incrementally without discarding the existing backend shape.

Finally, these directions are consistent with the stronger reference patterns. FastAPI explicitly supports shared resources via lifecycle hooks, but the stronger implementations still keep access paths explicit and dependency-driven. EasySQL already has the right lifecycle entrypoint; it now needs to stop leaking that lifecycle into process-global hidden state.

## Suggested Priority And Follow-up Questions

Priority:

- `P0`: remove the global service locator pattern from [easysql_api/deps.py](../easysql_api/deps.py), [easysql_api/infrastructure/db.py](../easysql_api/infrastructure/db.py), and the cached query-service access path.
- `P1`: decompose [query_service.py](../easysql_api/services/query_service.py) around orchestration, persistence coordination, and streaming concerns.
- `P1`: make runtime config refresh semantics explicit instead of relying on override mutation plus cache invalidation side effects.
- `P2`: encode message-to-turn relationships directly in persistence and simplify repository mapping.

Follow-up questions:

- Is in-process runtime configuration mutation a hard product requirement, or would controlled restart or rolling reload be acceptable?
- Is the API expected to run with multiple workers or multiple processes? If yes, current process-local override and cache semantics are a structural issue, not just a cleanliness issue.
- Should session-store schema readiness be managed by the app like the LangGraph checkpointer, or remain an external migration responsibility?
