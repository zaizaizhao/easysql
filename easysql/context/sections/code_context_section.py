"""
Code Context Section.

Renders code snippets from RAG for business logic context.
This is a placeholder for future implementation.
"""

from typing import List

from ..base import ContextSection
from ..models import ContextInput, SectionContent, CodeSnippet


class CodeContextSection(ContextSection):
    """
    Renders code context from RAG retrieval.
    
    Provides business logic context from actual codebase to help
    the LLM understand domain-specific patterns and conventions.
    
    Example output:
        ## 相关代码参考
        
        ### PatientService.get_patient_by_id
        **文件**: services/patient_service.py
        **说明**: 通过患者ID查询患者信息
        ```python
        def get_patient_by_id(self, patient_id: int) -> Patient:
            return self.session.query(Patient).filter(
                Patient.patient_id == patient_id
            ).first()
        ```
    
    Note:
        This section requires code_context in ContextInput.
        Code snippets should be retrieved via RAG from the codebase.
    """
    
    def __init__(
        self,
        max_snippets: int = 3,
        include_file_path: bool = True,
        include_description: bool = True,
        max_code_lines: int = 20,
    ):
        """
        Initialize code context section.
        
        Args:
            max_snippets: Maximum number of code snippets to include.
            include_file_path: Include file path for each snippet.
            include_description: Include description if available.
            max_code_lines: Maximum lines of code per snippet.
        """
        self._max_snippets = max_snippets
        self._include_file_path = include_file_path
        self._include_description = include_description
        self._max_code_lines = max_code_lines
    
    @property
    def name(self) -> str:
        return "code_context"
    
    def render(self, context: ContextInput) -> SectionContent:
        """Render code context."""
        snippets = context.code_context
        
        if not snippets:
            return SectionContent(
                name=self.name,
                content="",
                metadata={"reason": "no code context provided"}
            )
        
        # Sort by relevance and limit
        snippets = sorted(
            snippets,
            key=lambda x: x.relevance_score,
            reverse=True
        )[:self._max_snippets]
        
        lines = ["## 相关代码参考", ""]
        
        for snippet in snippets:
            # Title
            if snippet.class_name and snippet.method_name:
                title = f"### {snippet.class_name}.{snippet.method_name}"
            elif snippet.method_name:
                title = f"### {snippet.method_name}"
            elif snippet.class_name:
                title = f"### {snippet.class_name}"
            else:
                title = f"### 代码片段"
            
            lines.append(title)
            
            if self._include_file_path:
                lines.append(f"**文件**: {snippet.file_path}")
            
            if self._include_description and snippet.description:
                lines.append(f"**说明**: {snippet.description}")
            
            # Code block
            code_lines = snippet.code.split("\n")
            if len(code_lines) > self._max_code_lines:
                code = "\n".join(code_lines[:self._max_code_lines])
                code += "\n# ... (truncated)"
            else:
                code = snippet.code
            
            # Detect language from file extension
            lang = self._detect_language(snippet.file_path)
            
            lines.append(f"```{lang}")
            lines.append(code)
            lines.append("```")
            lines.append("")
        
        content = "\n".join(lines)
        
        return SectionContent(
            name=self.name,
            content=content,
            token_count=self.estimate_tokens(content),
            metadata={
                "snippet_count": len(snippets),
            }
        )
    
    def _detect_language(self, file_path: str) -> str:
        """Detect language from file extension."""
        ext_map = {
            ".py": "python",
            ".js": "javascript",
            ".ts": "typescript",
            ".java": "java",
            ".cs": "csharp",
            ".go": "go",
            ".rs": "rust",
            ".sql": "sql",
        }
        
        for ext, lang in ext_map.items():
            if file_path.endswith(ext):
                return lang
        
        return ""
