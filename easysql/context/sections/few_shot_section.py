"""
Few-Shot Section.

Renders few-shot examples for in-context learning.
This is a placeholder for future implementation.
"""

from typing import List

from ..base import ContextSection
from ..models import ContextInput, SectionContent, FewShotExample


class FewShotSection(ContextSection):
    """
    Renders few-shot examples for in-context learning.
    
    Provides SQL examples that help the LLM understand the expected
    query patterns and style.
    
    Example output:
        ## 参考示例
        
        **问题**: 查询所有住院患者
        **SQL**:
        ```sql
        SELECT * FROM patient WHERE status = '住院'
        ```
        
        **问题**: 统计各科室的患者数量
        **SQL**:
        ```sql
        SELECT d.name, COUNT(p.patient_id) as count
        FROM department d
        LEFT JOIN patient p ON d.department_id = p.department_id
        GROUP BY d.department_id
        ```
    
    Note:
        This section requires few_shot_examples in ContextInput.
        Examples can be retrieved from a vector database or predefined.
    """
    
    def __init__(
        self,
        max_examples: int = 3,
        include_explanation: bool = False,
        include_tables_used: bool = False,
    ):
        """
        Initialize few-shot section.
        
        Args:
            max_examples: Maximum number of examples to include.
            include_explanation: Include explanation for each example.
            include_tables_used: Include list of tables used.
        """
        self._max_examples = max_examples
        self._include_explanation = include_explanation
        self._include_tables_used = include_tables_used
    
    @property
    def name(self) -> str:
        return "few_shot"
    
    def render(self, context: ContextInput) -> SectionContent:
        """Render few-shot examples."""
        examples = context.few_shot_examples
        
        if not examples:
            return SectionContent(
                name=self.name,
                content="",
                metadata={"reason": "no examples provided"}
            )
        
        # Limit examples
        examples = examples[:self._max_examples]
        
        lines = ["## 参考示例", ""]
        
        for i, example in enumerate(examples, 1):
            lines.append(f"**示例 {i}**")
            lines.append(f"**问题**: {example.question}")
            
            if self._include_tables_used and example.tables_used:
                tables = ", ".join(example.tables_used)
                lines.append(f"**涉及表**: {tables}")
            
            lines.append("**SQL**:")
            lines.append("```sql")
            lines.append(example.sql)
            lines.append("```")
            
            if self._include_explanation and example.explanation:
                lines.append(f"**说明**: {example.explanation}")
            
            lines.append("")
        
        content = "\n".join(lines)
        
        return SectionContent(
            name=self.name,
            content=content,
            token_count=self.estimate_tokens(content),
            metadata={
                "example_count": len(examples),
            }
        )
