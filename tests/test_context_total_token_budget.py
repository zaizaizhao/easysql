from __future__ import annotations

from easysql.context.base import ContextSection, SectionConfig
from easysql.context.builder import ContextBuilder
from easysql.context.models import ContextInput, SectionContent
from easysql.retrieval.schema_retrieval import RetrievalResult


class _LargeSection(ContextSection):
    @property
    def name(self) -> str:
        return "large"

    def render(self, context: ContextInput) -> SectionContent:
        content = "x" * 20_000
        return SectionContent(
            name=self.name,
            content=content,
            token_count=self.estimate_tokens(content),
        )


class _LargeChineseSection(ContextSection):
    @property
    def name(self) -> str:
        return "large_chinese"

    def render(self, context: ContextInput) -> SectionContent:
        content = "患者放射治疗计划" * 3_000
        return SectionContent(
            name=self.name,
            content=content,
            token_count=self.estimate_tokens(content),
        )


def test_context_builder_enforces_max_total_tokens() -> None:
    builder = ContextBuilder(max_total_tokens=1_000)
    builder.add_section(_LargeSection(), SectionConfig(priority=0))
    context = ContextInput(
        question="test",
        retrieval_result=RetrievalResult(tables=[]),
    )

    output = builder.build(context)

    assert output.total_tokens <= 1_000
    assert "已截断" in output.user_prompt


def test_context_builder_enforces_max_total_tokens_for_chinese_content() -> None:
    builder = ContextBuilder(max_total_tokens=1_000)
    builder.add_section(_LargeChineseSection(), SectionConfig(priority=0))
    context = ContextInput(
        question="查询最近一次放射治疗计划",
        retrieval_result=RetrievalResult(tables=[]),
    )

    output = builder.build(context)

    assert output.total_tokens <= 1_000
    assert "已截断" in output.user_prompt
