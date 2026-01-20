"""
Prompt Templates for Context Builder.

Provides default and customizable prompt templates for Text2SQL.
"""

from dataclasses import dataclass
from typing import List, Optional
from pathlib import Path

from .models import SectionContent


# Default system prompt for Text2SQL
DEFAULT_SYSTEM_PROMPT = """你是一个专业的 SQL 专家，擅长将自然语言问题转换为 SQL 查询语句。

重要规则：
1. **严格限制**: 只使用下方提供的表和列，绝对不要假设或使用任何未提供的表
2. 如果所需的表或列未在提供的 schema 中，请明确说明"缺少必要的表: xxx"，而不是假设它存在
3. 使用标准 SQL 语法
4. 对于模糊查询使用 LIKE 操作符
5. 确保 JOIN 条件正确，使用提供的外键关系
6. 只返回 SQL 语句，不要添加解释
7. **禁止参数化语法**: 不要使用任何参数占位符如 %(name)s、%s、:name、? 等，必须生成可直接执行的完整 SQL
8. 如果用户问题中包含具体值（如患者ID、日期等），直接将值写入 SQL；如果没有具体值，使用合理的示例值或条件

输出格式：
- 只输出一条完整的、可直接执行的 SQL 查询语句
- 如果无法生成有效 SQL，输出: -- 缺少必要的表: [表名]"""

# Default user prompt template
DEFAULT_USER_PROMPT_TEMPLATE = """{sections}

---

**用户问题**: {question}

请生成正确的 SQL 查询语句："""


@dataclass
class PromptTemplate:
    """
    Prompt template configuration.

    Attributes:
        system_template: System prompt template.
        user_template: User prompt template with {sections} and {question} placeholders.
        section_separator: Separator between sections.
    """

    system_template: str
    user_template: str
    section_separator: str = "\n\n"

    @classmethod
    def default(cls) -> "PromptTemplate":
        """Create default Text2SQL template. factory mode"""
        return cls(
            system_template=DEFAULT_SYSTEM_PROMPT,
            user_template=DEFAULT_USER_PROMPT_TEMPLATE,
        )

    @classmethod
    def from_yaml(cls, path: str | Path) -> "PromptTemplate":
        """
        Load template from YAML file.

        Args:
            path: Path to YAML template file.

        Returns:
            PromptTemplate instance.

        YAML format:
            system_template: |
              You are a SQL expert...
            user_template: |
              {sections}

              Question: {question}
            section_separator: "\\n\\n"
        """
        import yaml  # type: ignore[import-untyped]

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)

        return cls(
            system_template=data.get("system_template", DEFAULT_SYSTEM_PROMPT),
            user_template=data.get("user_template", DEFAULT_USER_PROMPT_TEMPLATE),
            section_separator=data.get("section_separator", "\n\n"),
        )

    def render_system(self, **kwargs) -> str:
        """
        Render system prompt.

        Args:
            **kwargs: Optional variables for template substitution.

        Returns:
            Rendered system prompt.
        """
        template = self.system_template
        for key, value in kwargs.items():
            template = template.replace(f"{{{key}}}", str(value))
        return template

    def render_user(
        self,
        sections: List[SectionContent],
        question: str,
        **kwargs,
    ) -> str:
        """
        Render user prompt with sections.

        Args:
            sections: List of rendered section contents.
            question: User's question.
            **kwargs: Optional additional variables.

        Returns:
            Rendered user prompt.
        """
        # Join non-empty sections
        section_contents = [s.content for s in sections if s.content.strip()]
        sections_text = self.section_separator.join(section_contents)

        # Render template
        result = self.user_template.format(
            sections=sections_text,
            question=question,
            **kwargs,
        )

        return result
