"""Tests for the smart chunker service."""

import pytest

from app.models.schemas import FileChange
from app.services.chunker import SmartChunker


@pytest.fixture
def chunker():
    """Create a SmartChunker with test settings."""
    return SmartChunker()


def _make_file(path: str, patch: str = "test patch", status: str = "modified",
               additions: int = 5, deletions: int = 2) -> FileChange:
    """Helper to create a FileChange for testing."""
    return FileChange(
        file_path=path,
        status=status,
        additions=additions,
        deletions=deletions,
        patch=patch,
    )


class TestSmartChunker:
    def test_filter_removes_lock_files(self, chunker):
        files = [
            _make_file("app/main.py"),
            _make_file("package-lock.json"),
            _make_file("yarn.lock"),
        ]
        chunks = chunker.create_chunks(files)
        all_files = [f.file_path for chunk in chunks for f in chunk.files]

        assert "app/main.py" in all_files
        assert "package-lock.json" not in all_files
        assert "yarn.lock" not in all_files

    def test_filter_removes_binary_files(self, chunker):
        files = [
            _make_file("app/main.py"),
            _make_file("assets/logo.png"),
            _make_file("fonts/custom.woff"),
        ]
        chunks = chunker.create_chunks(files)
        all_files = [f.file_path for chunk in chunks for f in chunk.files]

        assert "app/main.py" in all_files
        assert "assets/logo.png" not in all_files

    def test_filter_removes_deleted_files(self, chunker):
        files = [
            _make_file("app/main.py"),
            _make_file("old_file.py", status="removed"),
        ]
        chunks = chunker.create_chunks(files)
        all_files = [f.file_path for chunk in chunks for f in chunk.files]

        assert "app/main.py" in all_files
        assert "old_file.py" not in all_files

    def test_filter_respects_ignored_paths(self, chunker):
        files = [
            _make_file("app/main.py"),
            _make_file("generated/output.py"),
        ]
        chunks = chunker.create_chunks(files, ignored_paths=["generated/*"])
        all_files = [f.file_path for chunk in chunks for f in chunk.files]

        assert "app/main.py" in all_files
        assert "generated/output.py" not in all_files

    def test_empty_files_returns_empty_chunks(self, chunker):
        chunks = chunker.create_chunks([])
        assert len(chunks) == 0

    def test_all_filtered_returns_empty_chunks(self, chunker):
        files = [
            _make_file("package-lock.json"),
        ]
        chunks = chunker.create_chunks(files)
        assert len(chunks) == 0

    def test_security_files_prioritized(self, chunker):
        files = [
            _make_file("utils/helpers.py"),
            _make_file("auth/login.py"),
            _make_file("styles/main.css", patch="test"),
        ]
        chunks = chunker.create_chunks(files)

        # Auth file should be in a higher-priority chunk
        assert len(chunks) > 0
        # The first chunk should contain the auth file (highest priority)
        first_chunk_files = [f.file_path for f in chunks[0].files]
        assert any("auth" in f for f in first_chunk_files)

    def test_count_tokens(self, chunker):
        tokens = chunker.count_tokens("Hello, world!")
        assert tokens > 0
        assert isinstance(tokens, int)

    def test_files_without_patches_filtered(self, chunker):
        files = [
            _make_file("app/main.py"),
            FileChange(
                file_path="binary.dll",
                status="modified",
                additions=0,
                deletions=0,
                patch="",
            ),
        ]
        chunks = chunker.create_chunks(files)
        all_files = [f.file_path for chunk in chunks for f in chunk.files]

        assert "app/main.py" in all_files
        assert "binary.dll" not in all_files
