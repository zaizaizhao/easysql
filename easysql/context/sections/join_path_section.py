"""
Join Path Section.

Renders FK join path information for SQL generation guidance.
"""

from typing import List, Dict

from ..base import ContextSection
from ..models import ContextInput, SectionContent


class JoinPathSection(ContextSection):
    """
    Renders JOIN path information between tables.
    
    Provides FK relationships for correct JOIN clause generation.
    
    Example output:
        ## JOIN 关系
        
        以下是表之间的外键关系，请使用这些关系进行 JOIN:
        
        - prescription.patient_id → patient.patient_id
        - prescription.doctor_id → employee.employee_id
        - fee_record.prescription_id → prescription.prescription_id
    """
    
    def __init__(
        self,
        include_header: bool = True,
        include_instructions: bool = True,
    ):
        """
        Initialize join path section.
        
        Args:
            include_header: Include section header.
            include_instructions: Include usage instructions.
        """
        self._include_header = include_header
        self._include_instructions = include_instructions
    
    @property
    def name(self) -> str:
        return "join_paths"
    
    def render(self, context: ContextInput) -> SectionContent:
        """Render JOIN path information."""
        result = context.retrieval_result
        
        if not result.join_paths:
            return SectionContent(
                name=self.name,
                content="",
                metadata={"reason": "no join paths"}
            )
        
        lines = []
        
        if self._include_header:
            lines.append("## JOIN 关系")
            lines.append("")
        
        if self._include_instructions:
            lines.append("以下是表之间的外键关系，请使用这些关系进行 JOIN:")
            lines.append("")
        
        # Render each join path
        for path in result.join_paths:
            fk_table = path.get("fk_table", "")
            pk_table = path.get("pk_table", "")
            fk_column = path.get("fk_column", "")
            pk_column = path.get("pk_column", "")
            
            if fk_table and pk_table and fk_column and pk_column:
                lines.append(f"- {fk_table}.{fk_column} → {pk_table}.{pk_column}")
        
        content = "\n".join(lines)
        
        return SectionContent(
            name=self.name,
            content=content,
            token_count=self.estimate_tokens(content),
            metadata={
                "join_path_count": len(result.join_paths),
            }
        )
