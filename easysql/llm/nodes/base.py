"""
Base Node Class.

Provides a base class for all LangGraph nodes with common utilities.
"""
import re
from abc import ABC, abstractmethod
from typing import Optional

from langchain_core.language_models import BaseChatModel

from easysql.llm.state import EasySQLState


class BaseNode(ABC):
    """Abstract base class for all EasySQL LangGraph nodes.
    
    Provides common utilities and enforces the callable interface.
    """
    
    @abstractmethod
    def __call__(self, state: EasySQLState) -> dict:
        """Process state and return updates.
        
        Args:
            state: Current graph state.
            
        Returns:
            Dictionary of state updates.
        """
        pass
    
    @staticmethod
    def extract_sql(content: str) -> str:
        """Extract SQL from markdown code blocks.
        
        Args:
            content: Raw LLM response content.
            
        Returns:
            Extracted SQL string.
        """
        # Try ```sql ... ```
        match = re.search(r"```sql\s*(.*?)\s*```", content, re.DOTALL | re.IGNORECASE)
        if match:
            return match.group(1).strip()
        
        # Try just ``` ... ```
        match = re.search(r"```\s*(.*?)\s*```", content, re.DOTALL)
        if match:
            return match.group(1).strip()
            
        # Assume entire content is SQL if no blocks
        return content.strip()
