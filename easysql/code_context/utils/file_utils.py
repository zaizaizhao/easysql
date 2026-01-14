from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path

EXTENSION_MAP: dict[str, str] = {
    ".cs": "csharp",
    ".py": "python",
    ".pyi": "python",
    ".java": "java",
    ".js": "javascript",
    ".jsx": "javascript",
    ".ts": "typescript",
    ".tsx": "typescript",
}

EXCLUDE_DIRS = {
    "node_modules",
    "bin",
    "obj",
    "dist",
    "build",
    "__pycache__",
    ".git",
    "venv",
    ".venv",
    "packages",
    ".vs",
    ".idea",
    "TestResults",
    "Debug",
    "Release",
}

EXCLUDE_PATTERNS = {
    "*.min.js",
    "*.bundle.js",
    "*.generated.cs",
    "*.Designer.cs",
    "AssemblyInfo.cs",
    "GlobalUsings.cs",
    "*.g.cs",
    "*.d.ts",
}


class LanguageDetector:
    def __init__(
        self,
        supported_languages: list[str] | None = None,
        exclude_dirs: set[str] | None = None,
        exclude_patterns: set[str] | None = None,
    ):
        self._supported = (
            set(supported_languages) if supported_languages else set(EXTENSION_MAP.values())
        )
        self._exclude_dirs = exclude_dirs or EXCLUDE_DIRS
        self._exclude_patterns = exclude_patterns or EXCLUDE_PATTERNS

    def detect(self, file_path: Path) -> str:
        suffix = file_path.suffix.lower()
        lang = EXTENSION_MAP.get(suffix, "unknown")
        if lang not in self._supported:
            return "unknown"
        return lang

    def should_process(self, file_path: Path) -> bool:
        for parent in file_path.parents:
            if parent.name in self._exclude_dirs:
                return False

        for pattern in self._exclude_patterns:
            if file_path.match(pattern):
                return False

        return self.detect(file_path) != "unknown"

    def scan_directory(self, root: Path) -> dict[str, list[Path]]:
        result: dict[str, list[Path]] = {}

        for file_path in root.rglob("*"):
            if not file_path.is_file():
                continue
            if not self.should_process(file_path):
                continue

            lang = self.detect(file_path)
            if lang not in result:
                result[lang] = []
            result[lang].append(file_path)

        return result


@dataclass
class FileChange:
    added: set[str]
    modified: set[str]
    deleted: set[str]

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.modified or self.deleted)

    @property
    def total_changes(self) -> int:
        return len(self.added) + len(self.modified) + len(self.deleted)


class FileTracker:
    def __init__(self, cache_path: Path):
        self._cache_path = cache_path
        self._hash_cache: dict[str, str] = self._load_cache()

    def _compute_hash(self, file_path: Path) -> str:
        content = file_path.read_bytes()
        return hashlib.md5(content).hexdigest()

    def detect_changes(self, current_files: dict[str, Path]) -> FileChange:
        added: set[str] = set()
        modified: set[str] = set()
        current_hashes: dict[str, str] = {}

        for rel_path, abs_path in current_files.items():
            file_hash = self._compute_hash(abs_path)
            current_hashes[rel_path] = file_hash

            if rel_path not in self._hash_cache:
                added.add(rel_path)
            elif self._hash_cache[rel_path] != file_hash:
                modified.add(rel_path)

        deleted = set(self._hash_cache.keys()) - set(current_files.keys())

        return FileChange(added=added, modified=modified, deleted=deleted)

    def update_cache(self, file_hashes: dict[str, str]) -> None:
        self._hash_cache.update(file_hashes)
        self._save_cache()

    def remove_from_cache(self, paths: set[str]) -> None:
        for path in paths:
            self._hash_cache.pop(path, None)
        self._save_cache()

    def clear_cache(self) -> None:
        self._hash_cache.clear()
        self._save_cache()

    def _load_cache(self) -> dict[str, str]:
        if self._cache_path.exists():
            try:
                data = json.loads(self._cache_path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    return {str(k): str(v) for k, v in data.items()}
                return {}
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _save_cache(self) -> None:
        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
        self._cache_path.write_text(
            json.dumps(self._hash_cache, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

    def get_file_hash(self, rel_path: str) -> str | None:
        return self._hash_cache.get(rel_path)

    @property
    def cached_file_count(self) -> int:
        return len(self._hash_cache)
