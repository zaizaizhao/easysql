"""
Schema Section.

Renders complete table schema information for LLM context.
"""

from typing import Literal, Set, List, Dict, Any

from ..base import ContextSection
from ..models import ContextInput, SectionContent


class SchemaSection(ContextSection):
    """
    Renders database schema information (complete table structure).
    
    Data source: RetrievalResult.table_columns (from Neo4j)
    
    Supports two output formats:
    - "table": Markdown table format (more readable)
    - "list": List format (more token-efficient)
    
    Example output (list format):
        ## 相关表结构
        
        ### patient (患者信息表)
        - patient_id: int (PK) - 患者ID
        - name: varchar(50) - 姓名
        - gender: char(1) - 性别
        
        ### prescription (处方表)
        - prescription_id: bigint (PK) - 处方ID
        - patient_id: int (FK→patient) - 患者ID
    """
    
    def __init__(
        self,
        format: Literal["table", "list"] = "list",
        include_types: bool = True,
        include_descriptions: bool = True,
        include_constraints: bool = True,
        max_columns_per_table: int = 50,
        highlight_semantic_columns: bool = False,
    ):
        """
        Initialize schema section.
        
        Args:
            format: Output format - "table" or "list".
            include_types: Include data types.
            include_descriptions: Include column descriptions.
            include_constraints: Include PK/FK/index info.
            max_columns_per_table: Maximum columns to show per table.
            highlight_semantic_columns: Highlight semantically relevant columns.
        """
        self._format = format
        self._include_types = include_types
        self._include_descriptions = include_descriptions
        self._include_constraints = include_constraints
        self._max_columns = max_columns_per_table
        self._highlight_semantic = highlight_semantic_columns
    
    @property
    def name(self) -> str:
        return "schema"
    
    def render(self, context: ContextInput) -> SectionContent:
        """Render complete table schema."""
        result = context.retrieval_result
        
        if not result.tables:
            return SectionContent(
                name=self.name,
                content="",
                metadata={"reason": "no tables"}
            )
        
        # Get semantic column names for highlighting
        semantic_cols: Set[str] = set()
        if self._highlight_semantic and result.semantic_columns:
            for col in result.semantic_columns:
                semantic_cols.add(f"{col.get('table_name', '')}.{col.get('column_name', '')}")
        
        lines = ["## 相关表结构", ""]
        
        for table_name in result.tables:
            columns = result.table_columns.get(table_name, [])
            metadata = result.table_metadata.get(table_name, {})
            
            # Table header
            chinese_name = metadata.get("chinese_name", "")
            if chinese_name:
                lines.append(f"### {table_name} ({chinese_name})")
            else:
                lines.append(f"### {table_name}")
            
            if not columns:
                lines.append("(无列信息)")
                lines.append("")
                continue
            
            # Limit columns
            display_columns = columns[:self._max_columns]
            truncated = len(columns) > self._max_columns
            
            if self._format == "table":
                lines.extend(self._render_table_format(
                    table_name, display_columns, semantic_cols
                ))
            else:
                lines.extend(self._render_list_format(
                    table_name, display_columns, semantic_cols
                ))
            
            if truncated:
                lines.append(f"... 还有 {len(columns) - self._max_columns} 列未显示")
            
            lines.append("")
        
        content = "\n".join(lines)
        
        return SectionContent(
            name=self.name,
            content=content,
            token_count=self.estimate_tokens(content),
            metadata={
                "tables": len(result.tables),
                "total_columns": sum(len(cols) for cols in result.table_columns.values()),
                "format": self._format,
            }
        )
    
    def _render_list_format(
        self,
        table_name: str,
        columns: List[Dict[str, Any]],
        semantic_cols: Set[str],
    ) -> List[str]:
        """Render columns in list format."""
        lines = []
        
        for col in columns:
            parts = []
            
            # Column name
            col_name = col.get("name", "")
            full_col_name = f"{table_name}.{col_name}"
            
            # Highlight if semantic
            if full_col_name in semantic_cols:
                parts.append(f"**{col_name}**")
            else:
                parts.append(col_name)
            
            # Data type
            if self._include_types:
                data_type = col.get("data_type", "")
                if data_type:
                    parts.append(f": {data_type}")
            
            # Constraints
            if self._include_constraints:
                constraints = []
                if col.get("is_pk"):
                    constraints.append("PK")
                if col.get("is_fk"):
                    constraints.append("FK")
                if col.get("is_unique") and not col.get("is_pk"):
                    constraints.append("UQ")
                if col.get("is_indexed") and not col.get("is_pk"):
                    constraints.append("IDX")
                
                if constraints:
                    parts.append(f" ({', '.join(constraints)})")
            
            # Description
            if self._include_descriptions:
                chinese_name = col.get("chinese_name", "")
                description = col.get("description", "")
                
                desc_text = chinese_name or description
                if desc_text:
                    parts.append(f" - {desc_text}")
            
            lines.append("- " + "".join(parts))
        
        return lines
    
    def _render_table_format(
        self,
        table_name: str,
        columns: List[Dict[str, Any]],
        semantic_cols: Set[str],
    ) -> List[str]:
        """Render columns in table format."""
        lines = []
        
        # Table header
        headers = ["列名"]
        if self._include_types:
            headers.append("类型")
        if self._include_descriptions:
            headers.append("说明")
        if self._include_constraints:
            headers.append("约束")
        
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["------"] * len(headers)) + "|")
        
        for col in columns:
            row = []
            
            # Column name
            col_name = col.get("name", "")
            full_col_name = f"{table_name}.{col_name}"
            
            if full_col_name in semantic_cols:
                row.append(f"**{col_name}**")
            else:
                row.append(col_name)
            
            # Data type
            if self._include_types:
                row.append(col.get("data_type", "-"))
            
            # Description
            if self._include_descriptions:
                chinese_name = col.get("chinese_name", "")
                description = col.get("description", "")
                row.append(chinese_name or description or "-")
            
            # Constraints
            if self._include_constraints:
                constraints = []
                if col.get("is_pk"):
                    constraints.append("PK")
                if col.get("is_fk"):
                    constraints.append("FK")
                if col.get("is_unique") and not col.get("is_pk"):
                    constraints.append("UQ")
                
                row.append(", ".join(constraints) if constraints else "-")
            
            lines.append("| " + " | ".join(row) + " |")
        
        return lines
