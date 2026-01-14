from pathlib import Path
from tempfile import TemporaryDirectory
from textwrap import dedent

import pytest

from easysql.code_context.chunker import CodeChunk, CodeChunker, ChunkResult
from easysql.code_context.utils import FileTracker, LanguageDetector, FileChange


class TestCodeChunker:
    def test_chunk_python_file(self, tmp_path: Path):
        chunker = CodeChunker(chunk_size=500, chunk_overlap=50)

        py_file = tmp_path / "example.py"
        py_file.write_text(
            dedent("""
            class User:
                def __init__(self, name: str):
                    self.name = name
                
                def greet(self) -> str:
                    return f"Hello, {self.name}"
            
            class Admin(User):
                def __init__(self, name: str, role: str):
                    super().__init__(name)
                    self.role = role
        """)
        )

        result = chunker.chunk_file(py_file, "python", "abc123")

        assert result.success
        assert len(result.chunks) >= 1
        assert result.chunks[0].language == "python"
        assert result.chunks[0].file_hash == "abc123"
        assert "User" in result.chunks[0].content

    def test_chunk_empty_file(self, tmp_path: Path):
        chunker = CodeChunker()

        empty_file = tmp_path / "empty.py"
        empty_file.write_text("")

        result = chunker.chunk_file(empty_file, "python", "empty")

        assert result.success
        assert len(result.chunks) == 0

    def test_chunk_id_format(self):
        chunk = CodeChunk(
            content="def foo(): pass",
            file_path="src/utils.py",
            file_hash="hash123",
            language="python",
            chunk_index=2,
        )

        assert chunk.chunk_id == "src/utils.py:2"

    def test_to_embedding_text(self):
        chunk = CodeChunk(
            content="class Order:\n    pass",
            file_path="models/order.py",
            file_hash="hash",
            language="python",
            chunk_index=0,
        )

        text = chunk.to_embedding_text()

        assert "file:order" in text
        assert "class Order:" in text

    def test_supported_languages(self):
        chunker = CodeChunker(supported_languages=["python", "java"])

        assert "python" in chunker.supported_languages
        assert "java" in chunker.supported_languages
        assert "csharp" not in chunker.supported_languages


class TestLanguageDetector:
    def test_detect_python(self):
        detector = LanguageDetector()

        assert detector.detect(Path("app.py")) == "python"
        assert detector.detect(Path("types.pyi")) == "python"

    def test_detect_csharp(self):
        detector = LanguageDetector()

        assert detector.detect(Path("User.cs")) == "csharp"

    def test_detect_typescript(self):
        detector = LanguageDetector()

        assert detector.detect(Path("app.ts")) == "typescript"
        assert detector.detect(Path("component.tsx")) == "typescript"

    def test_detect_unknown(self):
        detector = LanguageDetector()

        assert detector.detect(Path("readme.md")) == "unknown"
        assert detector.detect(Path("config.yaml")) == "unknown"

    def test_should_process_excludes_dirs(self):
        detector = LanguageDetector()

        assert detector.should_process(Path("src/app.py")) is True
        assert detector.should_process(Path("node_modules/lib.js")) is False
        assert detector.should_process(Path("bin/Debug/app.cs")) is False
        assert detector.should_process(Path("__pycache__/module.pyc")) is False

    def test_should_process_excludes_patterns(self):
        detector = LanguageDetector()

        assert detector.should_process(Path("src/app.min.js")) is False
        assert detector.should_process(Path("src/User.Designer.cs")) is False


class TestFileTracker:
    def test_detect_new_files(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        tracker = FileTracker(cache_path)

        file1 = tmp_path / "file1.py"
        file1.write_text("content1")

        changes = tracker.detect_changes({"file1.py": file1})

        assert "file1.py" in changes.added
        assert len(changes.modified) == 0
        assert len(changes.deleted) == 0
        assert changes.has_changes

    def test_detect_modified_files(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        tracker = FileTracker(cache_path)

        file1 = tmp_path / "file1.py"
        file1.write_text("content1")

        tracker.detect_changes({"file1.py": file1})
        tracker.update_cache({"file1.py": "old_hash"})

        file1.write_text("content2")
        changes = tracker.detect_changes({"file1.py": file1})

        assert "file1.py" in changes.modified

    def test_detect_deleted_files(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"
        tracker = FileTracker(cache_path)

        tracker.update_cache({"deleted.py": "hash"})

        changes = tracker.detect_changes({})

        assert "deleted.py" in changes.deleted

    def test_cache_persistence(self, tmp_path: Path):
        cache_path = tmp_path / "cache.json"

        tracker1 = FileTracker(cache_path)
        tracker1.update_cache({"file.py": "hash123"})

        tracker2 = FileTracker(cache_path)

        assert tracker2.get_file_hash("file.py") == "hash123"


class TestFileChange:
    def test_has_changes(self):
        no_changes = FileChange(added=set(), modified=set(), deleted=set())
        assert no_changes.has_changes is False

        with_added = FileChange(added={"file.py"}, modified=set(), deleted=set())
        assert with_added.has_changes is True

    def test_total_changes(self):
        changes = FileChange(
            added={"a.py", "b.py"},
            modified={"c.py"},
            deleted={"d.py", "e.py", "f.py"},
        )

        assert changes.total_changes == 6


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
