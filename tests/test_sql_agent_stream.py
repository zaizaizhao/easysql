"""Regression tests for SQL agent streaming content normalization."""

import asyncio

import pytest

from easysql.llm.nodes.sql_agent import SqlAgentNode


class DummyChunk:
    """Minimal stream chunk mock used by SqlAgentNode tests."""

    def __init__(self, content=None, tool_call_chunks=None):
        self.content = content
        self.tool_call_chunks = tool_call_chunks


class DummyLLM:
    """Minimal LLM stream mock implementing ``astream``."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def astream(self, _messages):
        for chunk in self._chunks:
            yield chunk


def test_stream_llm_response_handles_gemini_list_content() -> None:
    """Ensure Gemini-like list content is normalized without crashing."""
    node = SqlAgentNode()

    chunks = [
        DummyChunk(content=[{"text": "SELECT "}, {"text": "1"}], tool_call_chunks=[]),
        DummyChunk(content="\n", tool_call_chunks=[]),
        DummyChunk(
            content=None,
            tool_call_chunks=[
                {"index": 0, "name": "validate_sql", "id": "call_1", "args": '{"sql":"SELECT 1'}
            ],
        ),
        DummyChunk(content=None, tool_call_chunks=[{"index": 0, "args": '"}'}]),
    ]

    llm = DummyLLM(chunks)
    token_events: list[str] = []

    def writer(event: dict) -> None:
        if event.get("type") == "token":
            token_events.append(str(event.get("content", "")))

    message = asyncio.run(node._stream_llm_response(llm, [], writer, iteration=1))

    assert message.content == "SELECT 1\n"
    assert token_events == ["SELECT 1", "\n"]
    assert len(message.tool_calls) == 1
    assert message.tool_calls[0]["name"] == "validate_sql"
    assert message.tool_calls[0]["args"] == {"sql": "SELECT 1"}


def test_stream_llm_response_keeps_openai_like_string_content() -> None:
    """Ensure OpenAI/Kimi-like string chunks stay unchanged."""
    node = SqlAgentNode()

    chunks = [
        DummyChunk(content="SELECT ", tool_call_chunks=[]),
        DummyChunk(content="count(*)", tool_call_chunks=[]),
        DummyChunk(content=" FROM orders", tool_call_chunks=[]),
    ]

    llm = DummyLLM(chunks)
    message = asyncio.run(node._stream_llm_response(llm, [], writer=None, iteration=1))

    assert message.content == "SELECT count(*) FROM orders"
    assert message.tool_calls == []
