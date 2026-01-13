from pathlib import Path
from textwrap import dedent

import pytest

from easysql.code_context.models import LanguageType
from easysql.code_context.parsers import CSharpParser


class TestCSharpParser:
    def setup_method(self):
        self.parser = CSharpParser()

    def test_parse_simple_enum(self):
        content = dedent("""
            namespace Hospital.Domain
            {
                public enum PatientStatus
                {
                    [Description("待诊")]
                    Pending = 0,
                    [Description("就诊中")]
                    InTreatment = 1,
                    [Description("已出院")]
                    Discharged = 2,
                }
            }
        """)

        result = self.parser.parse_file(Path("test.cs"), content)

        assert result.success
        assert len(result.enums) == 1

        enum = result.enums[0]
        assert enum.name == "PatientStatus"
        assert enum.namespace == "Hospital.Domain"
        assert len(enum.values) == 3

        assert enum.values[0].name == "Pending"
        assert enum.values[0].value == 0
        assert enum.values[0].description == "待诊"

        assert enum.values[2].name == "Discharged"
        assert enum.values[2].value == 2
        assert enum.values[2].description == "已出院"

    def test_parse_entity_class(self):
        content = dedent("""
            namespace Hospital.Domain.Patients
            {
                [Table("patient")]
                public class Patient : AggregateRoot<long>
                {
                    [Key]
                    public long Id { get; set; }
                    
                    /// <summary>病历号</summary>
                    [Required]
                    public string MedicalRecordNo { get; set; }
                    
                    public string Name { get; set; }
                    
                    public PatientStatus Status { get; set; }
                    
                    public virtual ICollection<Visit> Visits { get; set; }
                }
            }
        """)

        result = self.parser.parse_file(Path("Patient.cs"), content)

        assert result.success
        assert len(result.entities) == 1

        entity = result.entities[0]
        assert entity.name == "Patient"
        assert entity.namespace == "Hospital.Domain.Patients"
        assert entity.mapped_table == "patient"
        assert entity.is_aggregate_root is True

        props = {p.name: p for p in entity.properties}
        assert "Id" in props
        assert props["Id"].is_key is True
        assert "MedicalRecordNo" in props
        assert props["MedicalRecordNo"].is_required is True
        assert "病历号" in (props["MedicalRecordNo"].description or "")
        assert "Visits" in props
        assert props["Visits"].is_navigation is True
        assert props["Visits"].is_collection is True

    def test_parse_enum_with_sequential_values(self):
        content = dedent("""
            public enum Permissions
            {
                None = 0,
                Read = 1,
                Write = 2,
                Execute = 4,
            }
        """)

        result = self.parser.parse_file(Path("Permissions.cs"), content)

        assert result.success
        assert len(result.enums) == 1

        enum = result.enums[0]
        values = {v.name: v.value for v in enum.values}
        assert values["None"] == 0
        assert values["Read"] == 1
        assert values["Write"] == 2
        assert values["Execute"] == 4

    def test_parse_file_scoped_namespace(self):
        content = dedent("""
            namespace Hospital.Domain.ValueObjects;
            
            public enum Gender
            {
                Unknown = 0,
                Male = 1,
                Female = 2,
            }
        """)

        result = self.parser.parse_file(Path("Gender.cs"), content)

        assert result.success
        assert len(result.enums) == 1
        assert result.enums[0].namespace == "Hospital.Domain.ValueObjects"

    def test_build_embedding_text(self):
        content = dedent("""
            public enum OrderStatus
            {
                [Description("待支付")]
                Pending = 0,
                [Description("已支付")]
                Paid = 1,
            }
        """)

        result = self.parser.parse_file(Path("test.cs"), content)
        enum = result.enums[0]

        text = enum.build_embedding_text()

        assert "OrderStatus" in text
        assert "Pending" in text
        assert "待支付" in text
        assert "Paid" in text
        assert "已支付" in text


class TestLanguageDetector:
    def test_detect_csharp(self):
        from easysql.code_context.utils import LanguageDetector

        detector = LanguageDetector()

        assert detector.detect(Path("Patient.cs")) == "csharp"
        assert detector.detect(Path("main.py")) == "python"
        assert detector.detect(Path("App.java")) == "java"
        assert detector.detect(Path("index.ts")) == "typescript"
        assert detector.detect(Path("unknown.xyz")) == "unknown"

    def test_should_process_excludes(self):
        from easysql.code_context.utils import LanguageDetector

        detector = LanguageDetector()

        assert detector.should_process(Path("src/Patient.cs")) is True
        assert detector.should_process(Path("bin/Debug/Patient.cs")) is False
        assert detector.should_process(Path("node_modules/lib.js")) is False
        assert detector.should_process(Path("src/Patient.Designer.cs")) is False


class TestFileTracker:
    def test_detect_changes(self, tmp_path):
        from easysql.code_context.utils import FileTracker

        cache_path = tmp_path / "cache.json"
        tracker = FileTracker(cache_path)

        file1 = tmp_path / "file1.cs"
        file1.write_text("content1")

        current_files = {"file1.cs": file1}
        changes = tracker.detect_changes(current_files)

        assert "file1.cs" in changes.added
        assert len(changes.modified) == 0
        assert len(changes.deleted) == 0

        tracker.update_cache({"file1.cs": "hash1"})

        file1.write_text("content2")
        changes = tracker.detect_changes(current_files)

        assert "file1.cs" in changes.modified

        changes = tracker.detect_changes({})
        assert "file1.cs" in changes.deleted


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
