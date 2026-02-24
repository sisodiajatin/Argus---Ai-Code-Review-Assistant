"""Tests for language-specific prompt hints."""

import pytest

from app.prompts.languages import get_language_hints, LANGUAGE_HINTS


class TestLanguageHints:
    def test_python_hint_exists(self):
        assert ".py" in LANGUAGE_HINTS
        label, hint = LANGUAGE_HINTS[".py"]
        assert label == "Python"
        assert "type hint" in hint.lower()

    def test_javascript_hint_exists(self):
        assert ".js" in LANGUAGE_HINTS
        label, hint = LANGUAGE_HINTS[".js"]
        assert label == "JavaScript"
        assert "var" in hint.lower() or "const" in hint.lower()

    def test_typescript_hint_exists(self):
        assert ".ts" in LANGUAGE_HINTS
        label, hint = LANGUAGE_HINTS[".ts"]
        assert label == "TypeScript"
        assert "any" in hint.lower()

    def test_go_hint_exists(self):
        assert ".go" in LANGUAGE_HINTS
        label, hint = LANGUAGE_HINTS[".go"]
        assert label == "Go"
        assert "error" in hint.lower()

    def test_rust_hint_exists(self):
        assert ".rs" in LANGUAGE_HINTS
        label, hint = LANGUAGE_HINTS[".rs"]
        assert label == "Rust"
        assert "unwrap" in hint.lower()

    def test_java_hint_exists(self):
        assert ".java" in LANGUAGE_HINTS
        label, hint = LANGUAGE_HINTS[".java"]
        assert label == "Java"
        assert "null" in hint.lower()


class TestGetLanguageHints:
    def test_single_extension(self):
        hints = get_language_hints({".py"})
        assert "Python" in hints
        assert len(hints) > 0

    def test_multiple_extensions(self):
        hints = get_language_hints({".py", ".ts"})
        assert "Python" in hints
        assert "TypeScript" in hints

    def test_unknown_extension_returns_empty(self):
        hints = get_language_hints({".xyz", ".unknown"})
        assert hints == ""

    def test_empty_set_returns_empty(self):
        hints = get_language_hints(set())
        assert hints == ""

    def test_aliases_work(self):
        # .mjs should map to JavaScript hints
        hints = get_language_hints({".mjs"})
        assert "JavaScript" in hints

    def test_cpp_alias(self):
        hints = get_language_hints({".hpp"})
        assert "C++" in hints

    def test_no_duplicate_labels(self):
        """If both .ts and .mts are present, TypeScript hints should appear only once."""
        hints = get_language_hints({".ts", ".mts"})
        assert hints.count("TypeScript-Specific Review Focus") == 1

    def test_tsx_hint_exists(self):
        hints = get_language_hints({".tsx"})
        assert "React" in hints
        assert "useEffect" in hints

    def test_shell_hint_exists(self):
        hints = get_language_hints({".sh"})
        assert "Shell" in hints or "Bash" in hints

    def test_sql_hint_exists(self):
        hints = get_language_hints({".sql"})
        assert "SQL" in hints
