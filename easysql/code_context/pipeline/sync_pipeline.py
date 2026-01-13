"""Code sync pipeline with incremental update support."""

from __future__ import annotations

import hashlib
import shutil
import tempfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from easysql.utils.logger import get_logger

if TYPE_CHECKING:
    from easysql.code_context.chunker import CodeChunker
    from easysql.code_context.storage.milvus_writer import CodeMilvusWriter
    from easysql.code_context.utils.file_utils import FileTracker, LanguageDetector

logger = get_logger(__name__)


@dataclass
class SyncResult:
    project_id: str
    files_added: int = 0
    files_modified: int = 0
    files_deleted: int = 0
    chunks_processed: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def total_files_changed(self) -> int:
        return self.files_added + self.files_modified + self.files_deleted

    def to_dict(self) -> dict[str, Any]:
        return {
            "project_id": self.project_id,
            "files_added": self.files_added,
            "files_modified": self.files_modified,
            "files_deleted": self.files_deleted,
            "chunks_processed": self.chunks_processed,
            "errors": self.errors,
            "success": self.success,
        }


class CodeSyncPipeline:
    def __init__(
        self,
        milvus_writer: "CodeMilvusWriter",
        file_tracker: "FileTracker",
        chunker: "CodeChunker",
        language_detector: "LanguageDetector | None" = None,
    ):
        self._milvus = milvus_writer
        self._tracker = file_tracker
        self._chunker = chunker
        self._detector = language_detector

    def _get_detector(self) -> "LanguageDetector":
        if self._detector is None:
            from easysql.code_context.utils.file_utils import LanguageDetector

            self._detector = LanguageDetector(
                supported_languages=list(self._chunker.supported_languages)
            )
        return self._detector

    def _compute_hash(self, file_path: Path) -> str:
        content = file_path.read_bytes()
        return hashlib.md5(content).hexdigest()

    def sync_from_zip(
        self,
        zip_path: Path | str,
        project_id: str,
    ) -> SyncResult:
        zip_path = Path(zip_path)

        if not zip_path.exists():
            return SyncResult(
                project_id=project_id,
                errors=[f"ZIP file not found: {zip_path}"],
            )

        with tempfile.TemporaryDirectory() as temp_dir:
            extract_path = Path(temp_dir)

            try:
                shutil.unpack_archive(str(zip_path), str(extract_path))
            except Exception as e:
                return SyncResult(
                    project_id=project_id,
                    errors=[f"Failed to extract ZIP: {e}"],
                )

            root_dirs = [d for d in extract_path.iterdir() if d.is_dir()]
            if len(root_dirs) == 1:
                extract_path = root_dirs[0]

            return self.sync_from_directory(
                root_path=extract_path,
                project_id=project_id,
            )

    def sync_from_directory(
        self,
        root_path: Path | str,
        project_id: str,
    ) -> SyncResult:
        root_path = Path(root_path)

        if not root_path.exists():
            return SyncResult(
                project_id=project_id,
                errors=[f"Directory not found: {root_path}"],
            )

        detector = self._get_detector()
        files_by_lang = detector.scan_directory(root_path)

        current_files: dict[str, tuple[Path, str]] = {}
        for lang, files in files_by_lang.items():
            for f in files:
                rel_path = f"{project_id}/{f.relative_to(root_path)}"
                current_files[rel_path] = (f, lang)

        path_to_abs = {k: v[0] for k, v in current_files.items()}
        changes = self._tracker.detect_changes(path_to_abs)

        logger.info(
            f"Project {project_id}: "
            f"added={len(changes.added)}, "
            f"modified={len(changes.modified)}, "
            f"deleted={len(changes.deleted)}"
        )

        result = SyncResult(
            project_id=project_id,
            files_added=len(changes.added),
            files_modified=len(changes.modified),
            files_deleted=len(changes.deleted),
        )

        if changes.deleted:
            try:
                self._milvus.delete_by_file_paths(changes.deleted)
                self._tracker.remove_from_cache(changes.deleted)
            except Exception as e:
                result.errors.append(f"Failed to delete old files: {e}")

        files_to_process = changes.added | changes.modified

        if not files_to_process:
            logger.info(f"No files to process for project {project_id}")
            return result

        files_for_chunking: list[tuple[Path, str, str]] = []
        new_hashes: dict[str, str] = {}

        for rel_path in files_to_process:
            abs_path, lang = current_files[rel_path]
            file_hash = self._compute_hash(abs_path)
            new_hashes[rel_path] = file_hash
            files_for_chunking.append((abs_path, lang, file_hash))

        chunk_result = self._chunker.chunk_files(files_for_chunking)

        for chunk in chunk_result.chunks:
            original_path = chunk.file_path
            for rel_path, (abs_path, _) in current_files.items():
                if str(abs_path) == original_path:
                    chunk.file_path = rel_path
                    break

        if chunk_result.errors:
            result.errors.extend(chunk_result.errors)

        if chunk_result.chunks:
            try:
                self._milvus.upsert_chunks(chunk_result.chunks)
                result.chunks_processed = len(chunk_result.chunks)
            except Exception as e:
                result.errors.append(f"Failed to store chunks: {e}")

        if new_hashes:
            self._tracker.update_cache(new_hashes)

        logger.info(f"Sync complete for {project_id}: chunks={result.chunks_processed}")

        return result

    def delete_project(self, project_id: str) -> int:
        deleted = self._milvus.delete_by_file_prefix(f"{project_id}/")
        self._tracker.clear_cache()

        logger.info(f"Deleted project {project_id}: chunks={deleted}")
        return deleted

    def get_stats(self) -> dict[str, Any]:
        return {
            "milvus": self._milvus.get_stats(),
            "cache": {
                "cached_files": self._tracker.cached_file_count,
            },
            "supported_languages": list(self._chunker.supported_languages),
        }
