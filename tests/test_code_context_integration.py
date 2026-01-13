from dataclasses import dataclass
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from easysql.code_context.models import CodeEntity, CodeEnum, EntityType, LanguageType
from easysql.code_context.parsers.java_parser import JavaParser
from easysql.code_context.parsers.python_parser import PythonParser
from easysql.code_context.storage.neo4j_writer import CodeNeo4jWriter
from easysql.repositories.neo4j_repository import Neo4jRepository


@dataclass
class MockNeo4jSession:
    run: MagicMock = MagicMock()
    execute_write: MagicMock = MagicMock()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass


class TestPythonParser:
    @pytest.fixture
    def parser(self):
        return PythonParser()

    def test_parse_simple_class(self, parser):
        content = """
class User:
    \"\"\"User entity.\"\"\"
    id: int
    name: str

    def get_name(self) -> str:
        return self.name
"""
        result = parser.parse_file(Path("user.py"), content)
        assert len(result.entities) == 1
        entity = result.entities[0]
        assert entity.name == "User"
        assert entity.description == "User entity."
        assert len(entity.properties) == 2
        assert entity.properties[0].name == "id"
        assert entity.properties[0].type_name == "int"
        assert len(entity.methods) == 1
        assert entity.methods[0].name == "get_name"

    def test_parse_pydantic_model(self, parser):
        content = """
from pydantic import BaseModel, Field

class Order(BaseModel):
    id: int = Field(..., description="Order ID")
    amount: float
"""
        result = parser.parse_file(Path("order.py"), content)
        assert len(result.entities) == 1
        entity = result.entities[0]
        assert entity.is_entity is True  # Because it inherits BaseModel
        assert entity.name == "Order"
        assert len(entity.properties) == 2

    def test_parse_enum(self, parser):
        content = """
from enum import Enum

class Status(Enum):
    \"\"\"Order status.\"\"\"
    PENDING = 1  # Waiting for payment
    PAID = 2
    SHIPPED = 3
"""
        result = parser.parse_file(Path("status.py"), content)
        assert len(result.enums) == 1
        enum = result.enums[0]
        assert enum.name == "Status"
        assert enum.description == "Order status."
        assert len(enum.values) == 3
        assert enum.values[0].name == "PENDING"
        assert enum.values[0].value == 1
        # Python AST parser might not capture inline comments easily without tokenizing,
        # but let's check if basic parsing works.

    def test_parse_table_name(self, parser):
        content = """
class Product:
    class Meta:
        table_name = "products"
"""
        result = parser.parse_file(Path("product.py"), content)
        assert result.entities[0].mapped_table == "products"


class TestJavaParser:
    @pytest.fixture
    def parser(self):
        return JavaParser()

    def test_parse_entity(self, parser):
        content = """
package com.example.domain;

/**
 * Patient entity.
 */
@Entity
@Table(name = "t_patient")
public class Patient {
    @Id
    private Long id;
    
    @Column(name = "full_name")
    private String name;
}
"""
        result = parser.parse_file(Path("Patient.java"), content)
        assert len(result.entities) == 1
        entity = result.entities[0]
        assert entity.name == "Patient"
        assert entity.namespace == "com.example.domain"
        assert entity.description == "Patient entity."
        assert entity.mapped_table == "t_patient"
        assert entity.is_entity is True

        assert len(result.entities[0].properties) == 2
        prop = result.entities[0].properties[1]
        assert prop.name == "name"
        assert prop.mapped_column == "full_name"

    def test_parse_enum(self, parser):
        content = """
public enum Gender {
    MALE,
    FEMALE
}
"""
        result = parser.parse_file(Path("Gender.java"), content)
        assert len(result.enums) == 1
        enum = result.enums[0]
        assert enum.name == "Gender"
        assert len(enum.values) == 2
        assert enum.values[0].name == "MALE"


class TestCodeNeo4jWriter:
    @pytest.fixture
    def mock_repo(self):
        repo = MagicMock(spec=Neo4jRepository)
        repo.database = "neo4j"
        repo.driver.session.return_value = MockNeo4jSession()
        return repo

    @pytest.fixture
    def writer(self, mock_repo):
        return CodeNeo4jWriter(mock_repo)

    def test_write_project_code(self, writer, mock_repo):
        entity = CodeEntity(
            id="test:User",
            file_path="User.py",
            file_hash="abc",
            language=LanguageType.PYTHON,
            entity_type=EntityType.CLASS,
            name="User",
            description="User entity",
            is_entity=True,
        )

        enum = CodeEnum(
            id="test:Status",
            file_path="Status.py",
            file_hash="def",
            language=LanguageType.PYTHON,
            name="Status",
            values=[],
        )

        writer.write_project_code("test_project", [entity], [enum])

        # Verify session usage
        session = mock_repo.driver.session.return_value
        assert session.execute_write.call_count >= 2  # At least entity + enum
