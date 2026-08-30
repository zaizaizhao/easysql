"""Render the selected single- or multi-database execution contract."""

from easysql.context.base import ContextSection
from easysql.context.models import ContextInput, SectionContent


class DatabaseScopeSection(ContextSection):
    @property
    def name(self) -> str:
        return "database_scope"

    def render(self, context: ContextInput) -> SectionContent:
        content = context.database_context or ""
        return SectionContent(
            name=self.name,
            content=content,
            token_count=self.estimate_tokens(content),
            metadata={"databases": context.db_names},
        )
