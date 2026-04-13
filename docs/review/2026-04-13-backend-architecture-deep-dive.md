# Backend Architecture Deep Dive

## Problem Statement

EasySQL’s backend packages look reasonably separated on disk, but runtime ownership is too implicit. Application services, repositories, engine state, and graph orchestration are shared through mutable process-global state, and `QueryService` has grown into a multi-responsibility orchestration surface. The result is a backend that feels more layered than it actually behaves at runtime.

## Current Architecture And Failure Surfaces

The main failure surfaces are all tied to ownership:

- startup installs process-global repository and config-service state in `deps.py` ([easysql_api/deps.py](../easysql_api/deps.py):12, [easysql_api/deps.py](../easysql_api/deps.py):20)
- DB engine and sessionmaker are global singletons in the infrastructure layer ([easysql_api/infrastructure/db.py](../easysql_api/infrastructure/db.py):10, [easysql_api/infrastructure/db.py](../easysql_api/infrastructure/db.py):24)
- `QueryService` caches graph and callback objects while also handling session lifecycle, branch behavior, persistence coordination, and streaming response shaping ([easysql_api/services/query_service.py](../easysql_api/services/query_service.py):24, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):540, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):666, [easysql_api/services/query_service.py](../easysql_api/services/query_service.py):902)
- session/message linkage is reconstructed heuristically in persistence, which means infrastructure code carries hidden product rules ([easysql_api/infrastructure/persistence/session_repository.py](../easysql_api/infrastructure/persistence/session_repository.py):320)

## Root Causes

The root cause is convenience-oriented growth around a small initial API surface. The project adopted a sensible top-level split between routers, services, and repositories, but runtime object ownership was handled with the lightest possible mechanism: module globals and singleton-style caches. That kept the code moving quickly, but as features such as branching, chart generation, config persistence, and LangGraph integration accumulated, more behavior was pulled into the same shared services.

There is also a mismatch between two backend styles in the same repo. `SchemaPipeline` is phase-oriented and locally owns its resources, while the API path is service-locator driven. That inconsistency makes it harder to establish one architectural default for future code.

## Strong Reference Patterns

The stronger pattern here is not “more layers”; it is explicit ownership:

- application resources created in `lifespan`
- app-scoped service container or `app.state`
- request-time dependencies resolved from explicit owners
- narrower application services with one dominant reason to change
- persistence models that encode relationships directly instead of reconstructing them heuristically

EasySQL already has some of those anchors, especially `lifespan` and the repository protocol. The missing piece is making those anchors the real runtime ownership model.

## Target Direction

The target backend shape should be:

- app-scoped ownership of initialized resources instead of module-global setters
- a thinner orchestration layer around query execution
- explicit sub-services for graph runtime coordination, session and turn persistence coordination, and transport or streaming shaping
- persistence models that directly encode message-to-turn relationships

This is an ownership refactor, not a wholesale redesign.

## Phased Optimization Plan

Phase 1:

- move repository, config service, and related long-lived resources into `app.state` or an explicit app container
- update dependencies to read from request-app context instead of globals

Phase 2:

- split `QueryService` into smaller services:
  graph runtime coordinator,
  session or turn persistence coordinator,
  stream response adapter

Phase 3:

- remove heuristic persistence mapping by storing message-to-turn linkage explicitly
- add backend tests around startup ownership and service replacement

Phase 4:

- align API orchestration style more closely with the local-ownership pattern already visible in `SchemaPipeline`

## Migration Risks And Decision Constraints

The main migration risk is accidentally breaking API behavior while untangling `QueryService`, because that service currently sits on the critical path for sessions, follow-ups, branching, and SSE output. Refactoring should preserve existing transport contracts and happen behind tests that pin those behaviors.

There is also a deployment constraint: if multi-worker or process-level scale-out matters, the move away from process-global singleton state becomes much higher priority. If deployment remains single-process for now, the same refactor is still valuable, but rollout can be more staged.
