"""Smart chunking service for preparing code diffs for LLM analysis.

Handles the critical challenge of fitting large PRs into LLM context windows
while preserving meaningful context. Uses file prioritization, logical grouping,
and token-aware splitting.
"""

import logging
import re
from pathlib import PurePosixPath

import tiktoken

from app.config import BaseAppSettings, get_base_settings
from app.models.schemas import FileChange, ReviewChunk

logger = logging.getLogger(__name__)

# File patterns that indicate higher risk and should be prioritized
HIGH_RISK_PATTERNS = [
    r"auth",
    r"login",
    r"password",
    r"secret",
    r"token",
    r"crypto",
    r"encrypt",
    r"security",
    r"permission",
    r"role",
    r"admin",
    r"api[/\\]",
    r"route",
    r"middleware",
    r"handler",
    r"controller",
    r"db[/\\]",
    r"database",
    r"migration",
    r"model",
    r"schema",
    r"query",
    r"sql",
    r"payment",
    r"billing",
    r"webhook",
]

# File patterns to deprioritize or skip
LOW_PRIORITY_PATTERNS = [
    r"-lock\.json$",
    r"\.lock$",
    r"\.min\.(js|css)$",
    r"\.generated\.",
    r"\.pb\.go$",
    r"__snapshots__",
    r"\.snap$",
    r"vendor[/\\]",
    r"node_modules[/\\]",
    r"\.svg$",
    r"\.png$",
    r"\.jpg$",
    r"\.ico$",
    r"\.woff",
    r"\.ttf$",
    r"\.eot$",
]

# File extensions grouped by language for logical grouping
LANGUAGE_GROUPS = {
    "python": {".py"},
    "javascript": {".js", ".jsx", ".mjs"},
    "typescript": {".ts", ".tsx"},
    "go": {".go"},
    "rust": {".rs"},
    "java": {".java"},
    "ruby": {".rb"},
    "config": {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg", ".env"},
    "docs": {".md", ".rst", ".txt"},
    "css": {".css", ".scss", ".less"},
}


class SmartChunker:
    """Breaks large PRs into LLM-friendly chunks with smart prioritization."""

    def __init__(self, settings: BaseAppSettings | None = None):
        self.settings = settings or get_base_settings()
        try:
            self._tokenizer = tiktoken.encoding_for_model(self.settings.ai_model)
        except KeyError:
            self._tokenizer = tiktoken.get_encoding("cl100k_base")

    def count_tokens(self, text: str) -> int:
        """Count the number of tokens in a text string."""
        return len(self._tokenizer.encode(text))

    def create_chunks(
        self,
        file_changes: list[FileChange],
        ignored_paths: list[str] | None = None,
    ) -> list[ReviewChunk]:
        """Create review chunks from file changes.

        This is the main entry point. It filters, prioritizes, groups,
        and splits files into token-aware chunks ready for LLM analysis.

        Args:
            file_changes: List of parsed file changes from the diff parser.
            ignored_paths: Optional list of glob patterns to ignore.

        Returns:
            List of ReviewChunk objects ordered by priority.
        """
        # Step 1: Filter out irrelevant files
        filtered = self._filter_files(file_changes, ignored_paths or [])

        if not filtered:
            logger.info("No reviewable files found in PR")
            return []

        # Step 2: Score and prioritize files
        scored_files = [(f, self._score_file(f)) for f in filtered]
        scored_files.sort(key=lambda x: x[1], reverse=True)

        # Step 3: Limit to max files
        max_files = self.settings.max_files_per_review
        if len(scored_files) > max_files:
            logger.info(f"Limiting review to {max_files} of {len(scored_files)} files")
            scored_files = scored_files[:max_files]

        # Step 4: Group related files
        groups = self._group_related_files([f for f, _ in scored_files])

        # Step 5: Split groups into token-aware chunks
        chunks = self._create_token_aware_chunks(groups, scored_files)

        logger.info(
            f"Created {len(chunks)} chunks from {len(filtered)} files "
            f"(filtered from {len(file_changes)} total)"
        )
        return chunks

    def _filter_files(
        self,
        files: list[FileChange],
        ignored_paths: list[str],
    ) -> list[FileChange]:
        """Filter out files that shouldn't be reviewed."""
        filtered = []
        for file in files:
            path = file.file_path

            # Skip files matching low-priority patterns
            if any(re.search(p, path, re.IGNORECASE) for p in LOW_PRIORITY_PATTERNS):
                logger.debug(f"Skipping low-priority file: {path}")
                continue

            # Skip files matching user-defined ignored paths
            if any(self._glob_match(path, pattern) for pattern in ignored_paths):
                logger.debug(f"Skipping ignored file: {path}")
                continue

            # Skip deleted files (nothing to review)
            if file.status == "removed":
                logger.debug(f"Skipping deleted file: {path}")
                continue

            # Skip empty patches (binary files, etc.)
            if not file.patch:
                logger.debug(f"Skipping file with no patch: {path}")
                continue

            filtered.append(file)
        return filtered

    def _score_file(self, file: FileChange) -> float:
        """Score a file by review priority (higher = more important).

        Factors:
        - High-risk filename patterns (auth, security, DB, etc.)
        - Change size (more changes = more risk)
        - File type (source code > config > docs)
        """
        score = 0.0
        path = file.file_path.lower()

        # High-risk pattern matching
        for pattern in HIGH_RISK_PATTERNS:
            if re.search(pattern, path, re.IGNORECASE):
                score += 10.0
                break  # Don't double-count

        # Change size factor (log scale to avoid huge files dominating)
        total_changes = file.additions + file.deletions
        if total_changes > 0:
            import math
            score += math.log2(total_changes + 1) * 2

        # File type scoring
        ext = PurePosixPath(file.file_path).suffix.lower()
        if ext in {".py", ".js", ".ts", ".jsx", ".tsx", ".go", ".rs", ".java", ".rb", ".c", ".cpp"}:
            score += 5.0  # Source code
        elif ext in {".json", ".yaml", ".yml", ".toml"}:
            score += 2.0  # Config files
        elif ext in {".md", ".rst", ".txt"}:
            score += 0.5  # Docs

        # Tests are important but slightly lower priority than source
        if "test" in path or "spec" in path:
            score *= 0.8

        return score

    def _group_related_files(self, files: list[FileChange]) -> list[list[FileChange]]:
        """Group related files together for coherent review chunks.

        Grouping strategy:
        1. Files in the same directory
        2. A source file and its test file
        3. Files with similar names (e.g., model + schema + route for same entity)
        """
        groups: list[list[FileChange]] = []
        assigned: set[str] = set()

        # First pass: pair source files with their tests
        file_map = {f.file_path: f for f in files}

        for file in files:
            if file.file_path in assigned:
                continue

            group = [file]
            assigned.add(file.file_path)

            # Look for related files
            base_path = PurePosixPath(file.file_path)
            stem = base_path.stem.replace("test_", "").replace("_test", "").replace(".test", "").replace(".spec", "")
            directory = str(base_path.parent)

            for other in files:
                if other.file_path in assigned:
                    continue

                other_path = PurePosixPath(other.file_path)
                other_dir = str(other_path.parent)
                other_stem = other_path.stem

                # Same directory
                is_same_dir = directory == other_dir

                # Test file pair
                is_test_pair = (
                    stem in other_stem or other_stem.replace("test_", "").replace("_test", "") == stem
                ) and is_same_dir

                # Related by name (e.g., user_model.py + user_service.py + user_route.py)
                is_name_related = stem.split("_")[0] == other_stem.split("_")[0] and is_same_dir

                if is_test_pair or is_name_related:
                    group.append(other)
                    assigned.add(other.file_path)

            groups.append(group)

        return groups

    def _create_token_aware_chunks(
        self,
        groups: list[list[FileChange]],
        scored_files: list[tuple[FileChange, float]],
    ) -> list[ReviewChunk]:
        """Split file groups into chunks that fit within the token limit."""
        score_map = {f.file_path: s for f, s in scored_files}
        token_limit = self.settings.chunk_token_limit
        chunks: list[ReviewChunk] = []
        chunk_id = 0

        current_files: list[FileChange] = []
        current_tokens = 0

        for group in groups:
            group_text = "\n".join(f.patch for f in group if f.patch)
            group_tokens = self.count_tokens(group_text)

            # If single group exceeds limit, split it
            if group_tokens > token_limit:
                # Flush current chunk first
                if current_files:
                    chunks.append(self._build_chunk(chunk_id, current_files, score_map))
                    chunk_id += 1
                    current_files = []
                    current_tokens = 0

                # Split large group into individual file chunks
                for file in group:
                    file_tokens = self.count_tokens(file.patch)
                    if file_tokens > token_limit:
                        # Single file exceeds limit - truncate it
                        truncated = self._truncate_file(file, token_limit)
                        chunks.append(self._build_chunk(chunk_id, [truncated], score_map))
                    else:
                        chunks.append(self._build_chunk(chunk_id, [file], score_map))
                    chunk_id += 1
                continue

            # Check if adding this group would exceed the limit
            if current_tokens + group_tokens > token_limit and current_files:
                chunks.append(self._build_chunk(chunk_id, current_files, score_map))
                chunk_id += 1
                current_files = []
                current_tokens = 0

            current_files.extend(group)
            current_tokens += group_tokens

        # Don't forget the last chunk
        if current_files:
            chunks.append(self._build_chunk(chunk_id, current_files, score_map))

        # Sort chunks by priority score
        chunks.sort(key=lambda c: c.priority_score, reverse=True)
        return chunks

    def _build_chunk(
        self,
        chunk_id: int,
        files: list[FileChange],
        score_map: dict[str, float],
    ) -> ReviewChunk:
        """Build a ReviewChunk from a list of files."""
        total_tokens = sum(self.count_tokens(f.patch) for f in files)
        avg_score = (
            sum(score_map.get(f.file_path, 0) for f in files) / len(files)
            if files
            else 0
        )
        context = f"Chunk with {len(files)} file(s): {', '.join(f.file_path for f in files)}"

        return ReviewChunk(
            chunk_id=f"chunk_{chunk_id}",
            files=files,
            context_summary=context,
            total_tokens_estimate=total_tokens,
            priority_score=avg_score,
        )

    def _truncate_file(self, file: FileChange, token_limit: int) -> FileChange:
        """Truncate a file's patch to fit within the token limit."""
        lines = file.patch.split("\n")
        truncated_lines = []
        current_tokens = 0

        for line in lines:
            line_tokens = self.count_tokens(line)
            if current_tokens + line_tokens > token_limit - 100:  # Reserve space for truncation notice
                truncated_lines.append("\n... [TRUNCATED - file too large for single chunk] ...")
                break
            truncated_lines.append(line)
            current_tokens += line_tokens

        return FileChange(
            file_path=file.file_path,
            status=file.status,
            old_path=file.old_path,
            additions=file.additions,
            deletions=file.deletions,
            patch="\n".join(truncated_lines),
            hunks=file.hunks,  # Keep original hunks for line mapping
        )

    @staticmethod
    def _glob_match(path: str, pattern: str) -> bool:
        """Simple glob-like matching for ignore patterns."""
        import fnmatch
        return fnmatch.fnmatch(path, pattern) or fnmatch.fnmatch(path.split("/")[-1], pattern)
