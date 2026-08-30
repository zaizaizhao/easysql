"""
Context Builder.

Orchestrates multiple context sections to build LLM prompts.
"""

from .base import ContextSection, SectionConfig
from .models import ContextInput, ContextOutput, SectionContent
from .sections import (
    CodeContextSection,
    DatabaseScopeSection,
    FewShotSection,
    JoinPathSection,
    SchemaSection,
)
from .templates import PromptTemplate


class ContextBuilder:
    """
    Context builder - orchestrates multiple sections to build LLM context.

    Usage:
        # Create with defaults
        builder = ContextBuilder.default()

        # Or customize
        builder = ContextBuilder()
        builder.add_section(SchemaSection(format="table"))
        builder.add_section(JoinPathSection())

        # Build context
        output = builder.build(context_input)

        # Use with LLM
        response = llm.chat(
            system=output.system_prompt,
            user=output.user_prompt,
        )
    """

    def __init__(
        self,
        template: PromptTemplate | None = None,
        max_total_tokens: int = 32000,
    ):
        """
        Initialize context builder.

        Args:
            template: Prompt template to use (default: PromptTemplate.default()).
            max_total_tokens: Maximum total tokens for the context.
        """
        self._sections: list[tuple[ContextSection, SectionConfig]] = []
        self._template = template or PromptTemplate.default()
        self._max_tokens = max_total_tokens

    def add_section(
        self,
        section: ContextSection,
        config: SectionConfig | None = None,
    ) -> "ContextBuilder":
        """
        Add a section to the builder.

        Args:
            section: Section instance to add.
            config: Optional section configuration.

        Returns:
            Self for chaining.
        """
        config = config or SectionConfig()
        self._sections.append((section, config))
        return self

    def remove_section(self, name: str) -> "ContextBuilder":
        """
        Remove a section by name.

        Args:
            name: Name of the section to remove.

        Returns:
            Self for chaining.
        """
        self._sections = [(s, c) for s, c in self._sections if s.name != name]
        return self

    def get_section(self, name: str) -> ContextSection | None:
        """
        Get a section by name.

        Args:
            name: Name of the section.

        Returns:
            Section instance or None if not found.
        """
        for section, _ in self._sections:
            if section.name == name:
                return section
        return None

    def build(self, context_input: ContextInput) -> ContextOutput:
        """
        Build the full context for LLM.

        Args:
            context_input: Context input with retrieval results.

        Returns:
            ContextOutput with system and user prompts.
        """
        # Render the non-section prompt first so the remaining section budget is real.
        system_prompt = self._template.render_system()
        empty_user_prompt = self._template.render_user(
            sections=[],
            question=context_input.question,
        )
        fixed_tokens = self._estimate_tokens(system_prompt) + self._estimate_tokens(
            empty_user_prompt
        )
        # Keep a small safety margin for section separators and estimator rounding.
        remaining_tokens = max(0, self._max_tokens - fixed_tokens - 16)

        # Sort sections by priority. Earlier sections consume the budget first.
        sorted_sections = sorted(self._sections, key=lambda x: x[1].priority)

        # Render each enabled section
        rendered_sections: list[SectionContent] = []
        has_non_empty_section = False

        for section, config in sorted_sections:
            if not config.enabled:
                continue

            content = section.render(context_input)

            # Apply the section-specific limit first.
            if config.max_tokens and content.token_count > config.max_tokens:
                content = self._truncate_section(content, config.max_tokens)

            if content.content.strip():
                separator_tokens = (
                    self._estimate_tokens(self._template.section_separator)
                    if has_non_empty_section
                    else 0
                )
                available_for_content = max(0, remaining_tokens - separator_tokens)
                if content.token_count > available_for_content:
                    content = self._truncate_section(content, available_for_content)
                if content.content.strip():
                    remaining_tokens = max(
                        0,
                        remaining_tokens
                        - separator_tokens
                        - self._estimate_tokens(content.content),
                    )
                    has_non_empty_section = True

            rendered_sections.append(content)

        # Render prompts
        user_prompt = self._template.render_user(
            sections=rendered_sections,
            question=context_input.question,
        )

        # Re-estimate the final rendered prompts instead of trusting section metadata.
        total_tokens = self._estimate_tokens(system_prompt) + self._estimate_tokens(user_prompt)

        return ContextOutput(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            sections=rendered_sections,
            total_tokens=total_tokens,
            metadata={
                "section_count": len(rendered_sections),
                "tables": context_input.retrieval_result.tables,
                "max_total_tokens": self._max_tokens,
                "truncated": any(s.metadata.get("truncated") for s in rendered_sections),
            },
        )

    def _truncate_section(
        self,
        content: SectionContent,
        max_tokens: int,
    ) -> SectionContent:
        """Truncate section content to fit token limit."""
        if max_tokens <= 0:
            return SectionContent(
                name=content.name,
                content="",
                token_count=0,
                metadata={**content.metadata, "truncated": bool(content.content)},
            )

        marker = "\n... (已截断)"
        if self._estimate_tokens(content.content) <= max_tokens:
            return content

        if self._estimate_tokens(marker) > max_tokens:
            return SectionContent(
                name=content.name,
                content="",
                token_count=0,
                metadata={**content.metadata, "truncated": True},
            )

        # Find the largest prefix that fits according to the same estimator used
        # for the final prompt. This is important for Chinese text, where a fixed
        # characters-per-token ratio can undercount by roughly 2x.
        low = 0
        high = len(content.content)
        while low < high:
            midpoint = (low + high + 1) // 2
            candidate = content.content[:midpoint] + marker
            if self._estimate_tokens(candidate) <= max_tokens:
                low = midpoint
            else:
                high = midpoint - 1

        truncated_content = content.content[:low] + marker

        return SectionContent(
            name=content.name,
            content=truncated_content,
            token_count=self._estimate_tokens(truncated_content),
            metadata={**content.metadata, "truncated": True},
        )

    def _estimate_tokens(self, text: str) -> int:
        """Estimate token count for text."""
        chinese_chars = sum(1 for c in text if "\u4e00" <= c <= "\u9fff")
        other_chars = len(text) - chinese_chars
        return int(chinese_chars / 1.5 + other_chars / 4)

    @classmethod
    def default(cls, db_type: str | None = None) -> "ContextBuilder":
        """
        Create a builder with default sections.

        Args:
            db_type: Database type for database-specific SQL rules.
                     Supported values: mysql, postgresql, oracle, sqlserver.

        Includes:
        - SchemaSection (priority 0)
        - FewShotSection (priority 5) - for in-context learning
        - JoinPathSection (priority 10)
        - CodeContextSection (priority 15) - renders empty when no code context

        Returns:
            Configured ContextBuilder instance.
        """
        template = PromptTemplate.default(db_type=db_type) if db_type else None
        builder = cls(template=template)
        builder.add_section(DatabaseScopeSection(), SectionConfig(priority=-10))
        builder.add_section(SchemaSection(), SectionConfig(priority=0))
        builder.add_section(
            FewShotSection(
                max_examples=3,
                include_explanation=True,
                include_tables_used=True,
            ),
            SectionConfig(priority=5),
        )
        builder.add_section(JoinPathSection(), SectionConfig(priority=10))
        builder.add_section(CodeContextSection(), SectionConfig(priority=15, max_tokens=2000))
        return builder

    @classmethod
    def minimal(cls) -> "ContextBuilder":
        """
        Create a minimal builder with compact schema.

        Uses list format and minimal options for token efficiency.
        Includes FewShotSection for in-context learning.

        Returns:
            Configured ContextBuilder instance.
        """
        builder = cls()
        builder.add_section(
            FewShotSection(
                max_examples=3,
                include_explanation=True,
                include_tables_used=True,
            ),
            SectionConfig(priority=5),
        )
        builder.add_section(JoinPathSection(), SectionConfig(priority=10))
        return builder
