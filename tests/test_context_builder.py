"""
Test Context Builder functionality.
"""

import pytest
from dataclasses import dataclass, field
from typing import List, Dict, Any

# Mock RetrievalResult for testing without database connections
@dataclass
class MockRetrievalResult:
    """Mock RetrievalResult for testing."""
    tables: List[str] = field(default_factory=list)
    table_columns: Dict[str, List[Dict[str, Any]]] = field(default_factory=dict)
    table_metadata: Dict[str, Dict[str, Any]] = field(default_factory=dict)
    semantic_columns: List[Dict[str, Any]] = field(default_factory=list)
    join_paths: List[Dict[str, str]] = field(default_factory=list)
    stats: Dict[str, Any] = field(default_factory=dict)


def create_test_retrieval_result():
    """Create a mock retrieval result for testing."""
    return MockRetrievalResult(
        tables=["patient", "prescription", "drug_dictionary"],
        table_columns={
            "patient": [
                {"name": "patient_id", "chinese_name": "患者ID", "data_type": "int", 
                 "is_pk": True, "is_fk": False, "is_nullable": False, "description": "主键"},
                {"name": "name", "chinese_name": "姓名", "data_type": "varchar(50)", 
                 "is_pk": False, "is_fk": False, "is_nullable": False, "description": None},
                {"name": "gender", "chinese_name": "性别", "data_type": "char(1)", 
                 "is_pk": False, "is_fk": False, "is_nullable": True, "description": "M/F"},
                {"name": "birth_date", "chinese_name": "出生日期", "data_type": "date", 
                 "is_pk": False, "is_fk": False, "is_nullable": True, "description": None},
            ],
            "prescription": [
                {"name": "prescription_id", "chinese_name": "处方ID", "data_type": "bigint", 
                 "is_pk": True, "is_fk": False, "is_nullable": False, "description": "主键"},
                {"name": "patient_id", "chinese_name": "患者ID", "data_type": "int", 
                 "is_pk": False, "is_fk": True, "is_nullable": False, "description": "外键关联患者"},
                {"name": "drug_id", "chinese_name": "药品ID", "data_type": "int", 
                 "is_pk": False, "is_fk": True, "is_nullable": False, "description": None},
                {"name": "dosage", "chinese_name": "剂量", "data_type": "varchar(100)", 
                 "is_pk": False, "is_fk": False, "is_nullable": True, "description": None},
                {"name": "created_at", "chinese_name": "开方时间", "data_type": "datetime", 
                 "is_pk": False, "is_fk": False, "is_nullable": False, "description": None},
            ],
            "drug_dictionary": [
                {"name": "drug_id", "chinese_name": "药品ID", "data_type": "int", 
                 "is_pk": True, "is_fk": False, "is_nullable": False, "description": None},
                {"name": "drug_name", "chinese_name": "药品名称", "data_type": "varchar(200)", 
                 "is_pk": False, "is_fk": False, "is_nullable": False, "description": None},
                {"name": "specification", "chinese_name": "规格", "data_type": "varchar(100)", 
                 "is_pk": False, "is_fk": False, "is_nullable": True, "description": None},
            ],
        },
        table_metadata={
            "patient": {"chinese_name": "患者信息表"},
            "prescription": {"chinese_name": "处方表"},
            "drug_dictionary": {"chinese_name": "药品字典"},
        },
        join_paths=[
            {"fk_table": "prescription", "pk_table": "patient", 
             "fk_column": "patient_id", "pk_column": "patient_id"},
            {"fk_table": "prescription", "pk_table": "drug_dictionary", 
             "fk_column": "drug_id", "pk_column": "drug_id"},
        ],
    )


class TestContextBuilder:
    """Test ContextBuilder class."""
    
    def test_default_builder_import(self):
        """Test that default builder can be created."""
        from easysql.context import ContextBuilder
        
        builder = ContextBuilder.default()
        assert builder is not None
        assert builder.get_section("schema") is not None
        assert builder.get_section("join_paths") is not None
    
    def test_minimal_builder(self):
        """Test minimal builder creation."""
        from easysql.context import ContextBuilder
        
        builder = ContextBuilder.minimal()
        assert builder is not None
    
    def test_add_remove_section(self):
        """Test adding and removing sections."""
        from easysql.context import ContextBuilder, SchemaSection
        
        builder = ContextBuilder()
        builder.add_section(SchemaSection())
        
        assert builder.get_section("schema") is not None
        
        builder.remove_section("schema")
        assert builder.get_section("schema") is None
    
    def test_build_context(self):
        """Test full context building."""
        from easysql.context import ContextBuilder, ContextInput
        
        # Create mock data
        result = create_test_retrieval_result()
        
        # Build context
        builder = ContextBuilder.default()
        context_input = ContextInput(
            question="查询所有患者的处方信息",
            retrieval_result=result,
        )
        
        output = builder.build(context_input)
        
        # Verify output
        assert output.system_prompt
        assert output.user_prompt
        assert "patient" in output.user_prompt
        assert "prescription" in output.user_prompt
        assert "查询所有患者的处方信息" in output.user_prompt
        assert len(output.sections) == 2  # schema + join_paths
        
        print("\n=== System Prompt ===")
        print(output.system_prompt)
        print("\n=== User Prompt ===")
        print(output.user_prompt)
        print(f"\n=== Total Tokens: {output.total_tokens} ===")


class TestSchemaSection:
    """Test SchemaSection class."""
    
    def test_list_format(self):
        """Test list format rendering."""
        from easysql.context import SchemaSection, ContextInput
        
        result = create_test_retrieval_result()
        context = ContextInput(question="test", retrieval_result=result)
        
        section = SchemaSection(format="list")
        content = section.render(context)
        
        assert content.name == "schema"
        assert "patient" in content.content
        assert "patient_id" in content.content
        assert "PK" in content.content
        
        print("\n=== List Format ===")
        print(content.content)
    
    def test_table_format(self):
        """Test table format rendering."""
        from easysql.context import SchemaSection, ContextInput
        
        result = create_test_retrieval_result()
        context = ContextInput(question="test", retrieval_result=result)
        
        section = SchemaSection(format="table")
        content = section.render(context)
        
        assert "|" in content.content  # Table format uses |
        
        print("\n=== Table Format ===")
        print(content.content)


class TestJoinPathSection:
    """Test JoinPathSection class."""
    
    def test_render(self):
        """Test JOIN path rendering."""
        from easysql.context import JoinPathSection, ContextInput
        
        result = create_test_retrieval_result()
        context = ContextInput(question="test", retrieval_result=result)
        
        section = JoinPathSection()
        content = section.render(context)
        
        assert "prescription.patient_id → patient.patient_id" in content.content
        assert "prescription.drug_id → drug_dictionary.drug_id" in content.content
        
        print("\n=== Join Paths ===")
        print(content.content)


class TestFewShotSection:
    """Test FewShotSection class."""
    
    def test_render_with_examples(self):
        """Test few-shot rendering with examples."""
        from easysql.context import FewShotSection, ContextInput, FewShotExample
        
        result = create_test_retrieval_result()
        context = ContextInput(
            question="test",
            retrieval_result=result,
            few_shot_examples=[
                FewShotExample(
                    question="查询所有患者",
                    sql="SELECT * FROM patient",
                    explanation="简单的全表查询",
                ),
                FewShotExample(
                    question="统计每个患者的处方数量",
                    sql="SELECT p.name, COUNT(pr.prescription_id) FROM patient p LEFT JOIN prescription pr ON p.patient_id = pr.patient_id GROUP BY p.patient_id",
                ),
            ],
        )
        
        section = FewShotSection(max_examples=2, include_explanation=True)
        content = section.render(context)
        
        assert "SELECT * FROM patient" in content.content
        assert "简单的全表查询" in content.content
        
        print("\n=== Few Shot Examples ===")
        print(content.content)


if __name__ == "__main__":
    # Run tests with verbose output
    test_builder = TestContextBuilder()
    test_builder.test_default_builder_import()
    test_builder.test_build_context()
    
    test_schema = TestSchemaSection()
    test_schema.test_list_format()
    test_schema.test_table_format()
    
    test_join = TestJoinPathSection()
    test_join.test_render()
    
    test_few = TestFewShotSection()
    test_few.test_render_with_examples()
    
    print("\n\n=== All tests passed! ===")
