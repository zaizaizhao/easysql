"""Regression tests for SQL agent streaming content normalization."""

import asyncio

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


class DummyFunctionChunk:
    """Minimal OpenAI delta.function chunk mock."""

    def __init__(self, name=None, arguments=None):
        self.name = name
        self.arguments = arguments


class DummyToolCallChunk:
    """Minimal OpenAI delta.tool_calls chunk mock."""

    def __init__(self, index=0, id=None, function=None):
        self.index = index
        self.id = id
        self.function = function


class DummyOpenAIDelta:
    """Minimal OpenAI delta mock."""

    def __init__(self, content=None, reasoning_content=None, tool_calls=None):
        self.content = content
        self.reasoning_content = reasoning_content
        self.tool_calls = tool_calls


class DummyOpenAIChoice:
    """Minimal OpenAI choice mock."""

    def __init__(self, delta):
        self.delta = delta


class DummyOpenAIChunk:
    """Minimal OpenAI stream chunk mock."""

    def __init__(self, delta):
        self.choices = [DummyOpenAIChoice(delta)]


class DummyOpenAIAsyncClient:
    """Minimal OpenAI async client mock implementing `create` stream."""

    def __init__(self, chunks):
        self._chunks = chunks

    async def create(self, **_kwargs):
        async def _stream():
            for chunk in self._chunks:
                yield chunk

        return _stream()


class DummyOpenAILLM:
    """Minimal ChatOpenAI-like model mock."""

    def __init__(self, model_name: str, openai_api_base: str, chunks):
        self.model_name = model_name
        self.openai_api_base = openai_api_base
        self.temperature = 1.0
        self.request_timeout = None
        self.async_client = DummyOpenAIAsyncClient(chunks)


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


def test_stream_llm_response_preserves_reasoning_content_for_replay() -> None:
    """Ensure reasoning_content survives assistant tool-call replay in Kimi path."""
    node = SqlAgentNode()

    chunks = [
        DummyOpenAIChunk(DummyOpenAIDelta(reasoning_content="思考1")),
        DummyOpenAIChunk(
            DummyOpenAIDelta(
                tool_calls=[
                    DummyToolCallChunk(
                        index=0,
                        id="call_1",
                        function=DummyFunctionChunk(name="validate_sql", arguments='{"sql":"SELECT '),
                    )
                ]
            )
        ),
        DummyOpenAIChunk(
            DummyOpenAIDelta(
                tool_calls=[
                    DummyToolCallChunk(
                        index=0,
                        function=DummyFunctionChunk(arguments='1"}'),
                    )
                ]
            )
        ),
    ]

    base_llm = DummyOpenAILLM(
        model_name="kimi-k2.5",
        openai_api_base="https://api.moonshot.cn/v1",
        chunks=chunks,
    )

    tools = [
        {
            "type": "function",
            "function": {
                "name": "validate_sql",
                "description": "validate sql",
                "parameters": {
                    "type": "object",
                    "properties": {"sql": {"type": "string"}},
                    "required": ["sql"],
                },
            },
        }
    ]

    message = asyncio.run(
        node._stream_llm_response(
            llm=DummyLLM([]),
            messages=[{"role": "user", "content": "test"}],
            writer=None,
            iteration=1,
            base_llm=base_llm,
            tools=tools,
        )
    )

    assert message.additional_kwargs["reasoning_content"] == "思考1"
    replay = message.additional_kwargs["_replay_message"]
    assert replay["reasoning_content"] == "思考1"
    assert replay["tool_calls"][0]["function"]["arguments"] == '{"sql":"SELECT 1"}'
    assert message.tool_calls[0]["name"] == "validate_sql"
    assert message.tool_calls[0]["args"] == {"sql": "SELECT 1"}


def test_should_use_openai_reasoning_roundtrip_only_for_kimi_path() -> None:
    kimi_llm = DummyOpenAILLM(
        model_name="kimi-k2.5",
        openai_api_base="https://api.moonshot.cn/v1",
        chunks=[],
    )
    non_kimi_llm = DummyOpenAILLM(
        model_name="gpt-4o",
        openai_api_base="https://api.openai.com/v1",
        chunks=[],
    )

    assert SqlAgentNode._should_use_openai_reasoning_roundtrip(kimi_llm) is True
    assert SqlAgentNode._should_use_openai_reasoning_roundtrip(non_kimi_llm) is False
