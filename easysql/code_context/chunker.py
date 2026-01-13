"""
Code Chunker - LangChain-based code splitting.

Uses LangChain's LanguageParser and RecursiveCharacterTextSplitter
for syntax-aware code chunking.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from easysql.utils.logger import get_logger

logger = get_logger(__name__)

# Language mapping: extension -> (langchain Language enum name, glob pattern)
LANGUAGE_CONFIG: dict[str, tuple[str, str]] = {
    "python": ("PYTHON", "**/*.py"),
    "csharp": ("CSHARP", "**/*.cs"),
    "java": ("JAVA", "**/*.java"),
    "javascript": ("JS", "**/*.js"),
    "typescript": ("TS", "**/*.ts"),
    "go": ("GO", "**/*.go"),
    "rust": ("RUST", "**/*.rs"),
    "cpp": ("CPP", "**/*.cpp"),
    "c": ("C", "**/*.c"),
}


@dataclass
class CodeChunk:
    """Represents a code chunk with metadata."""

    content: str
    file_path: str
    file_hash: str
    language: str
    chunk_index: int = 0
    metadata: dict[str, Any] = field(default_factory=dict)

    @property
    def chunk_id(self) -> str:
        """Generate unique ID for this chunk."""
        return f"{self.file_path}:{self.chunk_index}"

    def to_embedding_text(self) -> str:
        """Generate text for embedding."""
        # Include file path context for better retrieval
        file_name = Path(self.file_path).stem
        return f"file:{file_name}\n{self.content}"


@dataclass
class ChunkResult:
    """Result of chunking operation."""

    chunks: list[CodeChunk] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def success(self) -> bool:
        return len(self.errors) == 0

    @property
    def total_chunks(self) -> int:
        return len(self.chunks)


class CodeChunker:
    """
    LangChain-based code chunker.

    Uses RecursiveCharacterTextSplitter with language-specific separators
    to split code files into meaningful chunks.
    """

    def __init__(
        self,
        chunk_size: int = 2000,
        chunk_overlap: int = 200,
        supported_languages: list[str] | None = None,
    ):
        """
        Initialize the code chunker.

        Args:
            chunk_size: Maximum size of each chunk in characters.
            chunk_overlap: Overlap between adjacent chunks.
            supported_languages: List of supported languages. Defaults to all.
        """
        self._chunk_size = chunk_size
        self._chunk_overlap = chunk_overlap
        self._supported_languages = (
            set(supported_languages) if supported_languages else set(LANGUAGE_CONFIG.keys())
        )
        self._splitters: dict[str, Any] = {}

    def _get_splitter(self, language: str) -> Any:
        """Get or create a text splitter for the given language."""
        if language not in self._splitters:
            try:
                from langchain_text_splitters import Language, RecursiveCharacterTextSplitter

                lang_config = LANGUAGE_CONFIG.get(language)
                if not lang_config:
                    # Fallback to generic splitter
                    self._splitters[language] = RecursiveCharacterTextSplitter(
                        chunk_size=self._chunk_size,
                        chunk_overlap=self._chunk_overlap,
                    )
                else:
                    lang_enum_name = lang_config[0]
                    lang_enum = getattr(Language, lang_enum_name, None)
                    if lang_enum:
                        self._splitters[language] = RecursiveCharacterTextSplitter.from_language(
                            language=lang_enum,
                            chunk_size=self._chunk_size,
                            chunk_overlap=self._chunk_overlap,
                        )
                    else:
                        self._splitters[language] = RecursiveCharacterTextSplitter(
                            chunk_size=self._chunk_size,
                            chunk_overlap=self._chunk_overlap,
                        )
            except ImportError as e:
                logger.warning(f"langchain_text_splitters not available: {e}")
                # Return a simple fallback
                self._splitters[language] = None

        return self._splitters.get(language)

    def chunk_file(
        self,
        file_path: Path,
        language: str,
        file_hash: str,
    ) -> ChunkResult:
        """
        Chunk a single file.

        Args:
            file_path: Path to the file.
            language: Programming language of the file.
            file_hash: MD5 hash of the file content.

        Returns:
            ChunkResult with chunks and any errors.
        """
        chunks: list[CodeChunk] = []
        errors: list[str] = []

        try:
            content = file_path.read_text(encoding="utf-8", errors="replace")
        except OSError as e:
            return ChunkResult(errors=[f"Failed to read file {file_path}: {e}"])

        if not content.strip():
            return ChunkResult()

        splitter = self._get_splitter(language)

        if splitter is None:
            # Fallback: treat whole file as one chunk
            chunks.append(
                CodeChunk(
                    content=content[: self._chunk_size],
                    file_path=str(file_path),
                    file_hash=file_hash,
                    language=language,
                    chunk_index=0,
                )
            )
        else:
            try:
                text_chunks = splitter.split_text(content)
                for i, chunk_text in enumerate(text_chunks):
                    if chunk_text.strip():
                        chunks.append(
                            CodeChunk(
                                content=chunk_text,
                                file_path=str(file_path),
                                file_hash=file_hash,
                                language=language,
                                chunk_index=i,
                            )
                        )
            except Exception as e:
                errors.append(f"Failed to split {file_path}: {e}")
                # Fallback to simple chunking
                for i in range(0, len(content), self._chunk_size - self._chunk_overlap):
                    chunk_text = content[i : i + self._chunk_size]
                    if chunk_text.strip():
                        chunks.append(
                            CodeChunk(
                                content=chunk_text,
                                file_path=str(file_path),
                                file_hash=file_hash,
                                language=language,
                                chunk_index=i // (self._chunk_size - self._chunk_overlap),
                            )
                        )

        return ChunkResult(chunks=chunks, errors=errors)

    def chunk_files(
        self,
        files: list[tuple[Path, str, str]],
    ) -> ChunkResult:
        """
        Chunk multiple files.

        Args:
            files: List of (file_path, language, file_hash) tuples.

        Returns:
            Combined ChunkResult.
        """
        all_chunks: list[CodeChunk] = []
        all_errors: list[str] = []

        for file_path, language, file_hash in files:
            if language not in self._supported_languages:
                continue

            result = self.chunk_file(file_path, language, file_hash)
            all_chunks.extend(result.chunks)
            all_errors.extend(result.errors)

        return ChunkResult(chunks=all_chunks, errors=all_errors)

    @property
    def supported_languages(self) -> set[str]:
        return self._supported_languages
