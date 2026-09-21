from __future__ import annotations

from typing import Any

from google.adk.models import BaseLlm, LlmResponse
from google.genai import types
from pydantic import PrivateAttr


class ScriptedModel(BaseLlm):
    """Real ADK model interface with deterministic provider responses, not a mocked Runner."""

    model: str = "scripted"
    responses: list[dict[str, Any]]
    _index: int = PrivateAttr(default=0)

    async def generate_content_async(self, llm_request: Any, stream: bool = False) -> Any:
        if self._index >= len(self.responses):
            raise AssertionError("Unexpected additional model call")
        response = self.responses[self._index]
        self._index += 1
        if "tool" in response:
            part = types.Part(
                function_call=types.FunctionCall(
                    name=response["tool"], args=response.get("args", {}), id=f"call_{self._index}"
                )
            )
        else:
            part = types.Part(text=response["text"])
        parts = [part]
        if response.get("thought"):
            parts.insert(0, types.Part(text=response["thought"], thought=True))
        yield LlmResponse(content=types.Content(role="model", parts=parts), turn_complete=True)


class FakeCatalog:
    def table_schema(self, table_id: str) -> dict[str, Any]:
        return {
            "table_id": table_id,
            "columns": [{"name": "id", "data_type": "bigint"}],
            "foreign_keys": [],
            "primary_key": ["id"],
        }


class FakeExecutor:
    def __init__(self) -> None:
        self.requests = []

    def execute(self, request: Any) -> Any:
        from easysql.federation.executor import FederatedExecutionResult

        self.requests.append(request)
        return FederatedExecutionResult(success=True, row_count=1)
