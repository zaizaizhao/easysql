# Config And Runtime Review

## Scope And Thesis

This review covers the EasySQL configuration and runtime lane across docs, settings loading, API startup, runtime override persistence, editable config schema, and config-related tests. The main thesis is that EasySQL has the beginnings of a sensible FastAPI plus Pydantic settings setup, but it currently operates with multiple competing configuration authorities. That weakens source-of-truth clarity, makes live override safety more fragile than the docs imply, and leaves operators with an incomplete mental model of what actually wins when config values disagree.

## Current Implementation In EasySQL

The documented story says configuration comes from `.env` plus environment variables, and `docs/ENVIRONMENT.md` says the env-file path can be overridden through the CLI. The actual CLI does expose `--env`, but on the Typer callback and `config` command, not on a `run` subcommand, because there is no `run` command in the current CLI shape ([docs/ENVIRONMENT.md](../docs/ENVIRONMENT.md):3, [docs/ENVIRONMENT.md](../docs/ENVIRONMENT.md):10; [easysql/main.py](../easysql/main.py):18, [easysql/main.py](../easysql/main.py):27, [easysql/main.py](../easysql/main.py):30, [easysql/main.py](../easysql/main.py):140, [easysql/main.py](../easysql/main.py):182). This is the first visible sign that the operator contract and the implementation are drifting.

At the code level, the top-level `Settings` model is a cached `BaseSettings` object with `.env`, case-insensitive loading, and `extra="allow"` so dynamic `DB_<NAME>_*` groups can be parsed from merged input and `os.environ` ([easysql/config.py](../easysql/config.py):315, [easysql/config.py](../easysql/config.py):323, [easysql/config.py](../easysql/config.py):508, [easysql/config.py](../easysql/config.py):582). That part is coherent. The complication is that `LLMConfig`, `LangfuseConfig`, and `CheckpointerConfig` are also independent `BaseSettings` classes with their own `.env` declarations and `default_factory` construction inside `Settings` ([easysql/config.py](../easysql/config.py):131, [easysql/config.py](../easysql/config.py):194, [easysql/config.py](../easysql/config.py):224, [easysql/config.py](../easysql/config.py):489). In effect, EasySQL has one top-level settings object, but also several nested settings loaders.

The API startup path introduces a third authority. On startup the app requires PostgreSQL-backed session persistence, initializes the SQLAlchemy engine, constructs a config service, loads persisted config rows from the DB into runtime overrides, and then re-reads effective settings ([easysql_api/app.py](../easysql_api/app.py):25, [easysql_api/app.py](../easysql_api/app.py):30, [easysql_api/app.py](../easysql_api/app.py):33, [easysql_api/app.py](../easysql_api/app.py):52, [easysql_api/app.py](../easysql_api/app.py):53). Runtime overrides themselves are implemented as a global in-memory path map. `ConfigService.bootstrap_from_db()` calls `replace_runtime_overrides(...)`, request-time updates call `update_runtime_overrides(...)`, and `get_settings()` later applies those overrides by walking dotted paths and mutating an instantiated settings object with `setattr(...)` ([easysql/config.py](../easysql/config.py):23, [easysql/config.py](../easysql/config.py):53, [easysql/config.py](../easysql/config.py):590, [easysql_api/services/config_service.py](../easysql_api/services/config_service.py):44, [easysql_api/services/config_service.py](../easysql_api/services/config_service.py):63, [easysql_api/services/config_service.py](../easysql_api/services/config_service.py):165).

The editable persisted schema is not “all runtime config”; it is a curated subset. `CONFIG_SPEC_LIST` covers selected knobs across `llm`, `retrieval`, `few_shot`, `code_context`, and `langfuse`, but does not cover session store settings, checkpointer settings, source database groups, embedding configuration, logging, or Neo4j and Milvus endpoints ([easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py):146, [easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py):243, [easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py):351, [easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py):383, [easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py):415). The router then exposes several different views of configuration: assembled config, database config, editable config metadata, and persisted overrides ([easysql_api/routers/config.py](../easysql_api/routers/config.py):68, [easysql_api/routers/config.py](../easysql_api/routers/config.py):116, [easysql_api/routers/config.py](../easysql_api/routers/config.py):149, [easysql_api/routers/config.py](../easysql_api/routers/config.py):156).

There are also subtle runtime inconsistencies. The code documents `SESSION_POSTGRES_URI` as required, but `get_session_postgres_uri()` explicitly falls back to the checkpointer Postgres URI when the session URI is absent and the checkpointer is configured for Postgres ([easysql/config.py](../easysql/config.py):427, [easysql/config.py](../easysql/config.py):439). And while persisted config updates carry invalidation tags, not all LLM-related settings invalidate the compiled graph even though the graph structure and node-level caches may depend on them. `use_agent_mode` invalidates the graph, but many other LLM keys only invalidate `settings` ([easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py):146, [easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py):182, [easysql_api/services/config_schema.py](../easysql_api/services/config_schema.py):190; [easysql_api/services/config_service.py](../easysql_api/services/config_service.py):111).

The tests cover several useful pieces: schema mapping, config service persistence, config router behavior, LLM temperature configuration, and Langfuse alias precedence ([tests/test_config_schema.py](../tests/test_config_schema.py):13, [tests/test_config_service.py](../tests/test_config_service.py):84, [tests/test_config_router.py](../tests/test_config_router.py):60, [tests/test_llm_temperature_configurable.py](../tests/test_llm_temperature_configurable.py):5, [tests/test_langfuse_config.py](../tests/test_langfuse_config.py):4). What they do not currently prove is the full precedence story across alternate env files, nested settings loaders, DB overrides, and graph-cache invalidation.

## Comparison With Strong Reference Patterns

Pydantic Settings guidance strongly favors an explicit source-precedence model, ideally with one place to define custom sources and precedence. EasySQL diverges from that pattern by mixing top-level `Settings(_env_file=...)`, nested `BaseSettings` submodels with their own `.env` files, and a post-instantiation runtime override layer. The system can still work, but its precedence model is far less inspectable than the reference pattern.

FastAPI’s settings guidance favors a single cached `get_settings()` dependency and explicit dependency overrides in tests. EasySQL partially aligns here: it has a cached `get_settings()` and uses `Depends(get_settings_dep)` at the API layer. The divergence is that runtime behavior is also shaped by global singleton services and mutable process-wide override state, which makes the real effective config path more complex than the common FastAPI pattern suggests.

The 12-factor configuration principle assumes config is externalized and orthogonal. EasySQL still uses env-driven settings, but DB-persisted overrides and environment backfilling for Langfuse move the system away from a purely environment-sourced configuration model. That can be a valid product choice, but only if the precedence model is explicit and operator-visible.

## Review Findings

1. The core architectural issue is source-of-truth ambiguity. EasySQL currently has at least four relevant config authorities:
   top-level `Settings`,
   nested `BaseSettings` submodels,
   DB-persisted runtime overrides,
   and process-environment side effects for Langfuse.
   The system functions, but the precedence model is not explicit enough to reason about safely.

2. The documented alternate env-file override is likely only partially true. `load_settings(env_file)` passes `_env_file` to `Settings`, but the nested config models still declare their own `env_file=".env"`. That suggests `--env` may diverge between top-level fields and nested LLM, Langfuse, or checkpointer fields.

3. Runtime overrides are applied post-instantiation by walking dotted paths and calling `setattr(...)`. That means the authoritative validation boundary is split between Pydantic model construction and `ConfigSpec`-level validators. This is acceptable for simple scalar tuning knobs, but weaker than reconstructing one fully validated settings object from declared sources.

4. Live override safety is incomplete for the query lane. The compiled graph and several nodes cache config-dependent objects, but many LLM-related config keys only invalidate `settings` and not `graph`. The API can therefore accept and persist a config change that the in-memory graph may not actually pick up until a rebuild happens.

5. The persisted config control plane is too narrow to be a full runtime source of truth, but broad enough to create that expectation. It does not cover session store, checkpointer, embedding, database groups, logging, or storage endpoints, even though those settings materially affect whether the system can run.

6. The code and docs disagree on whether `SESSION_POSTGRES_URI` is truly required. The implementation explicitly allows fallback to the checkpointer Postgres URI, while the docs present the session URI as mandatory. That may be a deliberate convenience, but it is still an undocumented precedence edge.

7. Operability is hurt by config-surface noise. The docs still mention a nonexistent `run` subcommand, and operator-facing configuration references include stale, unused, or not-yet-wired variables. That makes the configuration surface look larger and less stable than it really is.

## Optimization Directions

1. Collapse configuration loading to one authoritative settings boundary. The cleanest shape is a top-level `Settings` as the only `BaseSettings`, with nested submodels converted to plain `BaseModel` structures. Then define source precedence once and explicitly.

2. Replace post-instantiation `setattr(...)` overrides with a declared settings source or a settings rebuild step. If DB-persisted overrides are a product feature, construct a fresh validated `Settings` object from explicit precedence rather than mutating a cached instance in place.

3. Tie live config changes to the runtime objects they actually affect. Any LLM or graph-affecting key should either invalidate and rebuild the compiled graph, or nodes should stop caching config- and model-dependent objects across requests.

4. Decide whether persisted config is “tuning only” or “full runtime config.” If it is tuning only, say so clearly in docs and UI. If it is intended to be a real control plane, extend the schema coverage to session, checkpointer, storage, and related runtime boundaries.

5. Reduce operator-facing config noise. Remove stale `run` wording, move unsupported or future variables out of the main operator docs, and separate supported runtime knobs, legacy aliases, and non-runtime placeholders.

6. Add precedence and staleness tests:
   alternate `--env` propagation into nested settings,
   DB override precedence over env and defaults,
   and proof that live config changes actually take effect in the query lane.

## Why These Changes Are Justified

The single biggest risk in this lane is not “a bad default”; it is ambiguity. When operators cannot tell whether `.env`, alternate env files, DB rows, nested submodels, or in-memory mutation wins, the system becomes hard to debug even if each mechanism works in isolation.

The current override path is also only partially safe for live systems because the API can accept and persist changes that the query graph may not actually observe until caches are rebuilt. That is a correctness issue, not just a style issue.

Finally, the persisted config surface is currently large enough to create control-plane expectations, but too narrow to fully describe runtime state. Clarifying what it is for, and enforcing one explicit precedence model, will reduce both operator confusion and runtime drift.

## Suggested Priority And Follow-up Questions

Priority:

- `P0`: unify config source precedence and remove the split between top-level and nested settings loaders.
- `P0`: make live LLM and query config changes either rebuild the graph or stop caching stale config and LLM instances.
- `P1`: make docs and `.env.example` reflect the real runtime contract, especially around `--env`, session persistence, and unused variables.
- `P1`: decide whether DB-persisted config is an authoritative control plane or a limited tuning layer, then align schema, UI, and docs to that decision.
- `P2`: extend tests to cover precedence and staleness boundaries that the current suite does not prove.

Follow-up questions:

- Should session store and checkpointer settings remain strictly env-only operational config, or are they intended to become editable through the API control plane?
- Is the product requirement that runtime config changes take effect immediately for running API instances, or is restart-level consistency acceptable?
- Should DB-persisted overrides outrank process environment, or should env remain the emergency operator override above persisted state?
- Is Langfuse environment backfilling only a compatibility bridge, or an intentional long-term design?
