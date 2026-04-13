# Config And Runtime Deep Dive

## Problem Statement

EasySQL currently has multiple competing configuration authorities: top-level `Settings`, nested `BaseSettings` submodels, DB-persisted runtime overrides, and selected environment-variable backfills for Langfuse. The system works, but it is no longer obvious which layer is authoritative, when a live change takes effect, or which runtime objects must be rebuilt after configuration changes.

## Current Architecture And Failure Surfaces

The top-level settings model is env-driven and cached, but `LLMConfig`, `LangfuseConfig`, and `CheckpointerConfig` also load from `.env` independently through `default_factory` construction ([easysql/config.py](../easysql/config.py):131, [easysql/config.py](../easysql/config.py):194, [easysql/config.py](../easysql/config.py):224, [easysql/config.py](../easysql/config.py):315). API startup then loads DB-persisted overrides into a global runtime-override map and reuses `get_settings()` as if a single authoritative settings object still exists ([easysql_api/app.py](../easysql_api/app.py):52, [easysql/config.py](../easysql/config.py):582, [easysql_api/services/config_service.py](../easysql_api/services/config_service.py):44, [easysql_api/services/config_service.py](../easysql_api/services/config_service.py):165).

The immediate failure surfaces are:

- alternate `--env` behavior may not propagate consistently into nested settings loaders
- persisted config can report success even when the compiled graph or node-level caches keep stale values
- the control plane only covers part of the runtime, so operators can mistake “editable config” for “full runtime config”
- the documented requirement for `SESSION_POSTGRES_URI` is softened in code by fallback to the checkpointer Postgres URI ([easysql/config.py](../easysql/config.py):439)

## Root Causes

The root cause is incremental growth without a single precedence model. The project started from straightforward env-based configuration, then added nested settings classes for clearer grouping, then added DB-persisted tuning controls, then added cache invalidation and environment backfill behavior to make selected live changes work. Each addition is reasonable on its own, but together they create a configuration system that behaves more like a partially implicit control plane than a single settings model.

There is also a product-boundary issue. The project has not yet decided whether persisted config is only for safe tuning knobs or whether it is intended to become the authoritative runtime control plane. Without that decision, the code and docs oscillate between those two interpretations.

## Strong Reference Patterns

The stronger reference pattern is one authoritative settings boundary plus explicit precedence. In practice, that means:

- one `BaseSettings` entrypoint
- nested structures as plain models rather than nested loaders
- one declared source order such as defaults -> env file -> environment -> persisted overrides
- explicit refresh or rebuild semantics for runtime objects that depend on those settings

FastAPI’s standard pattern also assumes `get_settings()` is the authoritative dependency surface. EasySQL already looks like that at the API boundary, which means the main work is reducing hidden extra sources behind the same interface rather than inventing a new surface.

## Target Direction

The target direction should be:

- top-level `Settings` remains the only `BaseSettings`
- nested config classes become plain `BaseModel` sections
- DB overrides become either a declared custom source or a rebuild step that returns a new validated `Settings` instance
- each persisted config key declares which runtime objects must be rebuilt or reloaded
- persisted config is explicitly labeled as either “tuning control plane” or “full runtime control plane”

This keeps the current product behavior possible while making precedence inspectable and testable.

## Phased Optimization Plan

Phase 1:

- document the current real precedence model
- fix the stale `run` wording in docs
- add tests for `--env`, DB override precedence, and graph-staleness after live config changes

Phase 2:

- collapse nested settings loaders into plain nested models under one `Settings`
- remove post-instantiation `setattr(...)` mutation in favor of reconstructing validated settings from explicit sources

Phase 3:

- decide whether persisted config is tuning-only or authoritative runtime control
- align `config_schema.py`, UI exposure, and operator docs to that decision

Phase 4:

- if live changes remain a requirement, make graph and model caches explicit refreshable components with deterministic invalidation semantics

## Migration Risks And Decision Constraints

The main migration risk is breaking assumed precedence for existing deployments. Some current behavior may be relying on the nested `.env` loaders or on fallback session-store resolution. Before changing precedence, the project needs an explicit decision on whether environment variables remain the emergency override above persisted DB config.

There is also a runtime-consistency constraint: if multi-worker deployment is expected, a process-local in-memory override model is not enough. That question should be answered before investing heavily in “live config” semantics that only hold inside one process.
