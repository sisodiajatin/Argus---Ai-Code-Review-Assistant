"""Tests for the diff parser service."""

import pytest

from app.services.diff_parser import DiffParser
from app.services.vcs.base import PRFile


@pytest.fixture
def parser():
    return DiffParser()


@pytest.fixture
def sample_patch():
    return """@@ -1,5 +1,7 @@
 import os
+import sys
 
 def hello():
-    print("hello")
+    print("hello world")
+    return True
 """


@pytest.fixture
def multi_hunk_patch():
    return """@@ -1,4 +1,5 @@
 import os
+import sys
 
 def hello():
     print("hello")
@@ -10,4 +11,5 @@
 
 def goodbye():
-    print("bye")
+    print("goodbye")
+    return False
 """


class TestDiffParser:
    def test_parse_simple_patch(self, parser, sample_patch):
        pr_file = PRFile(
            filename="test.py",
            status="modified",
            additions=3,
            deletions=1,
            patch=sample_patch,
        )
        results = parser.parse_pr_files([pr_file])

        assert len(results) == 1
        file_change = results[0]
        assert file_change.file_path == "test.py"
        assert file_change.status == "modified"
        assert len(file_change.hunks) == 1

    def test_parse_hunk_lines(self, parser, sample_patch):
        pr_file = PRFile(
            filename="test.py",
            status="modified",
            additions=3,
            deletions=1,
            patch=sample_patch,
        )
        results = parser.parse_pr_files([pr_file])
        hunk = results[0].hunks[0]

        # Check that we have the right line types
        add_lines = [l for l in hunk.lines if l.line_type == "add"]
        delete_lines = [l for l in hunk.lines if l.line_type == "delete"]
        context_lines = [l for l in hunk.lines if l.line_type == "context"]

        assert len(add_lines) == 3  # import sys, print("hello world"), return True
        assert len(delete_lines) == 1  # print("hello")
        assert len(context_lines) >= 2  # import os, def hello():

    def test_parse_multi_hunk(self, parser, multi_hunk_patch):
        pr_file = PRFile(
            filename="test.py",
            status="modified",
            additions=3,
            deletions=1,
            patch=multi_hunk_patch,
        )
        results = parser.parse_pr_files([pr_file])
        assert len(results[0].hunks) == 2

    def test_parse_added_file(self, parser):
        patch = """@@ -0,0 +1,3 @@
+def new_function():
+    return 42
+"""
        pr_file = PRFile(
            filename="new_file.py",
            status="added",
            additions=3,
            deletions=0,
            patch=patch,
        )
        results = parser.parse_pr_files([pr_file])
        assert results[0].status == "added"
        assert len(results[0].hunks) == 1
        assert all(l.line_type == "add" for l in results[0].hunks[0].lines)

    def test_parse_empty_patch(self, parser):
        pr_file = PRFile(
            filename="binary_file.png",
            status="modified",
            additions=0,
            deletions=0,
            patch=None,
        )
        results = parser.parse_pr_files([pr_file])
        assert len(results) == 1
        assert results[0].patch == ""
        assert len(results[0].hunks) == 0

    def test_get_changed_line_numbers(self, parser, sample_patch):
        pr_file = PRFile(
            filename="test.py",
            status="modified",
            additions=3,
            deletions=1,
            patch=sample_patch,
        )
        results = parser.parse_pr_files([pr_file])
        changed_lines = parser.get_changed_line_numbers(results[0])

        assert len(changed_lines) == 3
        assert all(isinstance(ln, int) for ln in changed_lines)

    def test_format_diff_for_llm(self, parser, sample_patch):
        pr_file = PRFile(
            filename="test.py",
            status="modified",
            additions=3,
            deletions=1,
            patch=sample_patch,
        )
        results = parser.parse_pr_files([pr_file])
        formatted = parser.format_diff_for_llm(results[0])

        assert "## File: test.py" in formatted
        assert "modified" in formatted
        assert "+" in formatted  # Has added lines
        assert "-" in formatted  # Has deleted lines

    def test_hunk_header_parsing(self, parser):
        patch = """@@ -10,5 +20,8 @@ def some_function():
 context line
+added line
"""
        pr_file = PRFile(
            filename="test.py",
            status="modified",
            additions=1,
            deletions=0,
            patch=patch,
        )
        results = parser.parse_pr_files([pr_file])
        hunk = results[0].hunks[0]

        assert hunk.old_start == 10
        assert hunk.old_count == 5
        assert hunk.new_start == 20
        assert hunk.new_count == 8
        assert "some_function" in hunk.header
