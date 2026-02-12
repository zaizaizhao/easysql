"""Editable runtime configuration schema for API-driven overrides."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Literal

ConfigValueType = Literal["str", "int", "float", "bool", "null"]
Validator = Callable[[Any], None]
ConstraintCode = Literal[
    "enum_plan_fast",
    "gt_0",
    "ge_0",
    "ge_1",
    "between_0_1",
    "between_0_2",
    "non_empty",
    "nullable",
]

VALIDATOR_CONSTRAINT_MAP: dict[str, ConstraintCode] = {
    "_validate_query_mode": "enum_plan_fast",
    "_validate_positive_int": "gt_0",
    "_validate_non_negative_int": "ge_0",
    "_validate_at_least_one": "ge_1",
    "_validate_probability": "between_0_1",
    "_validate_temperature": "between_0_2",
    "_validate_non_empty": "non_empty",
}

ENV_VAR_OVERRIDES: dict[tuple[str, str], str] = {
    ("llm", "temperature"): "LLM_TEMPERATURE",
    ("langfuse", "host"): "LANGFUSE_BASE_URL",
}


@dataclass(frozen=True)
class ConfigSpec:
    """Definition of an editable runtime configuration key."""

    category: str
    key: str
    settings_path: str
    env_var: str
    value_type: ConfigValueType
    nullable: bool = False
    secret: bool = False
    validator: Validator | None = None
    constraints: tuple[ConstraintCode, ...] = ()
    invalidate_tags: frozenset[str] = frozenset()


def _derive_constraints(
    validator: Validator | None,
    nullable: bool,
    constraints: list[ConstraintCode] | None = None,
) -> tuple[ConstraintCode, ...]:
    values: list[ConstraintCode] = []

    if constraints is not None:
        values.extend(constraints)
    elif validator is not None:
        mapped = VALIDATOR_CONSTRAINT_MAP.get(validator.__name__)
        if mapped is not None:
            values.append(mapped)

    if nullable and "nullable" not in values:
        values.append("nullable")

    return tuple(values)


def _derive_env_var(category: str, key: str) -> str:
    override = ENV_VAR_OVERRIDES.get((category, key))
    if override is not None:
        return override

    if category == "langfuse":
        return f"LANGFUSE_{key.upper()}"

    return key.upper()


def _validate_query_mode(value: Any) -> None:
    if value not in {"plan", "fast"}:
        raise ValueError("query_mode must be one of: plan, fast")


def _validate_positive_int(value: Any) -> None:
    if value <= 0:
        raise ValueError("value must be > 0")


def _validate_non_negative_int(value: Any) -> None:
    if value < 0:
        raise ValueError("value must be >= 0")


def _validate_at_least_one(value: Any) -> None:
    if value < 1:
        raise ValueError("value must be >= 1")


def _validate_probability(value: Any) -> None:
    if value < 0 or value > 1:
        raise ValueError("value must be in [0, 1]")


def _validate_temperature(value: Any) -> None:
    if value < 0 or value > 2:
        raise ValueError("value must be in [0, 2]")


def _validate_non_empty(value: Any) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError("value must be a non-empty string")


def _spec(
    category: str,
    key: str,
    settings_path: str,
    value_type: ConfigValueType,
    *,
    nullable: bool = False,
    secret: bool = False,
    validator: Validator | None = None,
    constraints: list[ConstraintCode] | None = None,
    invalidate_tags: set[str] | None = None,
) -> ConfigSpec:
    return ConfigSpec(
        category=category,
        key=key,
        settings_path=settings_path,
        env_var=_derive_env_var(category, key),
        value_type=value_type,
        nullable=nullable,
        secret=secret,
        validator=validator,
        constraints=_derive_constraints(validator, nullable, constraints),
        invalidate_tags=frozenset(invalidate_tags or {"settings"}),
    )


CONFIG_SPEC_LIST: list[ConfigSpec] = [
    # llm
    _spec(
        "llm",
        "query_mode",
        "llm.query_mode",
        "str",
        validator=_validate_query_mode,
        invalidate_tags={"settings"},
    ),
    _spec("llm", "openai_llm_model", "llm.openai_llm_model", "str", invalidate_tags={"settings"}),
    _spec(
        "llm",
        "google_llm_model",
        "llm.google_llm_model",
        "str",
        nullable=True,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm",
        "anthropic_llm_model",
        "llm.anthropic_llm_model",
        "str",
        nullable=True,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm",
        "model_planning",
        "llm.model_planning",
        "str",
        nullable=True,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm",
        "temperature",
        "llm.temperature",
        "float",
        validator=_validate_temperature,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm", "use_agent_mode", "llm.use_agent_mode", "bool", invalidate_tags={"settings", "graph"}
    ),
    _spec(
        "llm",
        "agent_max_iterations",
        "llm.agent_max_iterations",
        "int",
        validator=_validate_positive_int,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm",
        "max_sql_retries",
        "llm.max_sql_retries",
        "int",
        validator=_validate_positive_int,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm",
        "openai_api_key",
        "llm.openai_api_key",
        "str",
        nullable=True,
        secret=True,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm",
        "openai_api_base",
        "llm.openai_api_base",
        "str",
        nullable=True,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm",
        "google_api_key",
        "llm.google_api_key",
        "str",
        nullable=True,
        secret=True,
        invalidate_tags={"settings"},
    ),
    _spec(
        "llm",
        "anthropic_api_key",
        "llm.anthropic_api_key",
        "str",
        nullable=True,
        secret=True,
        invalidate_tags={"settings"},
    ),
    # retrieval
    _spec(
        "retrieval",
        "retrieval_search_top_k",
        "retrieval_search_top_k",
        "int",
        validator=_validate_positive_int,
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "retrieval_expand_fk",
        "retrieval_expand_fk",
        "bool",
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "retrieval_expand_max_depth",
        "retrieval_expand_max_depth",
        "int",
        validator=_validate_non_negative_int,
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "semantic_filter_enabled",
        "semantic_filter_enabled",
        "bool",
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "semantic_filter_threshold",
        "semantic_filter_threshold",
        "float",
        validator=_validate_probability,
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "semantic_filter_min_tables",
        "semantic_filter_min_tables",
        "int",
        validator=_validate_at_least_one,
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "bridge_protection_enabled",
        "bridge_protection_enabled",
        "bool",
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "bridge_max_hops",
        "bridge_max_hops",
        "int",
        validator=_validate_at_least_one,
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "core_tables",
        "core_tables",
        "str",
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "llm_filter_enabled",
        "llm_filter_enabled",
        "bool",
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "llm_filter_max_tables",
        "llm_filter_max_tables",
        "int",
        validator=_validate_positive_int,
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "llm_filter_model",
        "llm_filter_model",
        "str",
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "llm_api_key",
        "llm_api_key",
        "str",
        nullable=True,
        secret=True,
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    _spec(
        "retrieval",
        "llm_api_base",
        "llm_api_base",
        "str",
        nullable=True,
        invalidate_tags={"settings", "retrieval_cache"},
    ),
    # few-shot
    _spec(
        "few_shot",
        "few_shot_enabled",
        "few_shot_enabled",
        "bool",
        invalidate_tags={"settings", "few_shot_cache"},
    ),
    _spec(
        "few_shot",
        "few_shot_max_examples",
        "few_shot_max_examples",
        "int",
        validator=_validate_positive_int,
        invalidate_tags={"settings", "few_shot_cache"},
    ),
    _spec(
        "few_shot",
        "few_shot_min_similarity",
        "few_shot_min_similarity",
        "float",
        validator=_validate_probability,
        invalidate_tags={"settings", "few_shot_cache"},
    ),
    _spec(
        "few_shot",
        "few_shot_collection_name",
        "few_shot_collection_name",
        "str",
        validator=_validate_non_empty,
        invalidate_tags={"settings", "few_shot_cache"},
    ),
    # code_context
    _spec(
        "code_context",
        "code_context_enabled",
        "code_context_enabled",
        "bool",
        invalidate_tags={"settings", "code_context_cache"},
    ),
    _spec(
        "code_context",
        "code_context_search_top_k",
        "code_context_search_top_k",
        "int",
        validator=_validate_positive_int,
        invalidate_tags={"settings", "code_context_cache"},
    ),
    _spec(
        "code_context",
        "code_context_score_threshold",
        "code_context_score_threshold",
        "float",
        validator=_validate_probability,
        invalidate_tags={"settings", "code_context_cache"},
    ),
    _spec(
        "code_context",
        "code_context_max_snippets",
        "code_context_max_snippets",
        "int",
        validator=_validate_positive_int,
        invalidate_tags={"settings", "code_context_cache"},
    ),
    # langfuse
    _spec(
        "langfuse",
        "enabled",
        "langfuse.enabled",
        "bool",
        invalidate_tags={"settings", "callbacks", "langfuse_env"},
    ),
    _spec(
        "langfuse",
        "host",
        "langfuse.host",
        "str",
        validator=_validate_non_empty,
        invalidate_tags={"settings", "callbacks", "langfuse_env"},
    ),
    _spec(
        "langfuse",
        "public_key",
        "langfuse.public_key",
        "str",
        nullable=True,
        secret=True,
        invalidate_tags={"settings", "callbacks", "langfuse_env"},
    ),
    _spec(
        "langfuse",
        "secret_key",
        "langfuse.secret_key",
        "str",
        nullable=True,
        secret=True,
        invalidate_tags={"settings", "callbacks", "langfuse_env"},
    ),
]

CONFIG_SPECS: dict[tuple[str, str], ConfigSpec] = {
    (item.category, item.key): item for item in CONFIG_SPEC_LIST
}

CATEGORIES: set[str] = {item.category for item in CONFIG_SPEC_LIST}


def get_spec(category: str, key: str) -> ConfigSpec:
    spec = CONFIG_SPECS.get((category, key))
    if spec is None:
        raise KeyError(f"Unsupported config key: {category}.{key}")
    return spec


def get_category_specs(category: str) -> list[ConfigSpec]:
    if category not in CATEGORIES:
        raise KeyError(f"Unsupported config category: {category}")
    return [item for item in CONFIG_SPEC_LIST if item.category == category]


def serialize_value(value: Any) -> tuple[str, str]:
    if value is None:
        return "null", ""

    if isinstance(value, bool):
        return "bool", "true" if value else "false"

    if isinstance(value, int):
        return "int", str(value)

    if isinstance(value, float):
        return "float", repr(value)

    if isinstance(value, str):
        return "str", value

    raise TypeError(f"Unsupported config value type: {type(value).__name__}")


def deserialize_value(raw_value: str, value_type: str) -> Any:
    if value_type == "null":
        return None

    if value_type == "bool":
        lower = raw_value.lower()
        if lower == "true":
            return True
        if lower == "false":
            return False
        raise ValueError(f"Invalid bool value: {raw_value}")

    if value_type == "int":
        return int(raw_value)

    if value_type == "float":
        return float(raw_value)

    if value_type == "str":
        return raw_value

    raise ValueError(f"Unsupported config value_type: {value_type}")
