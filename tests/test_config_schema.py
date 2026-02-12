from __future__ import annotations

import pytest

from easysql_api.services.config_schema import (
    CONFIG_SPEC_LIST,
    deserialize_value,
    get_spec,
    serialize_value,
)


def test_config_schema_contains_expected_keys() -> None:
    assert get_spec("llm", "query_mode").settings_path == "llm.query_mode"
    assert get_spec("llm", "query_mode").env_var == "QUERY_MODE"
    assert get_spec("llm", "temperature").settings_path == "llm.temperature"
    assert get_spec("llm", "temperature").env_var == "LLM_TEMPERATURE"
    assert "between_0_2" in get_spec("llm", "temperature").constraints
    assert get_spec("llm", "openai_api_base").settings_path == "llm.openai_api_base"
    assert get_spec("langfuse", "host").env_var == "LANGFUSE_BASE_URL"
    assert len(CONFIG_SPEC_LIST) >= 36


def test_serialize_deserialize_round_trip() -> None:
    cases = [
        "abc",
        123,
        0.25,
        True,
        False,
        None,
    ]

    for case in cases:
        value_type, raw = serialize_value(case)
        parsed = deserialize_value(raw, value_type)
        assert parsed == case


def test_deserialize_invalid_bool_raises() -> None:
    with pytest.raises(ValueError):
        deserialize_value("not-bool", "bool")
