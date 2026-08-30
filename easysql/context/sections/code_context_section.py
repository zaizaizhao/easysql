"""
Code Context Section.

Renders code snippets related to the query (retrieved from the code
knowledge base) as a proper prompt section, so they participate in the
same priority / token-budget / truncation rules as every other section.
"""

from ..base import ContextSection
from ..models import ContextInput, SectionContent


class CodeContextSection(ContextSection):
    """
    Renders retrieved code context.

    The content is produced by CodeRetrievalService.retrieve_formatted()
    and passed through ContextInput.code_context. When absent, the section
    renders empty and is skipped by the template.
    """

    @property
    def name(self) -> str:
        return "code_context"

    def render(self, context: ContextInput) -> SectionContent:
        code_context = context.code_context

        if not code_context:
            return SectionContent(
                name=self.name,
                content="",
                metadata={"reason": "no code context provided"},
            )

        return SectionContent(
            name=self.name,
            content=code_context,
            token_count=self.estimate_tokens(code_context),
            metadata={"length": len(code_context)},
        )
