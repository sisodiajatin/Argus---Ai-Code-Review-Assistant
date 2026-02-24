"""Tests for the CLI output formatters."""

import json

import pytest

from cli.formatters import (
    RichFormatter,
    JSONFormatter,
    PlainFormatter,
    get_formatter,
    SEVERITY_STYLES,
    CATEGORY_ICONS,
)
from app.services.review_pipeline import ReviewResult
from app.models.schemas import AIFinding


@pytest.fixture
def empty_result():
    return ReviewResult(
        files_reviewed=3,
        chunks_processed=1,
        model_used="test-model",
        tokens_used=50,
        processing_time_ms=200.0,
    )


@pytest.fixture
def result_with_findings():
    return ReviewResult(
        findings=[
            AIFinding(
                file_path="app/main.py",
                line_start=10,
                line_end=15,
                category="bug",
                severity="critical",
                title="Null reference",
                description="Variable could be None",
                suggested_fix="Add null check",
            ),
            AIFinding(
                file_path="app/utils.py",
                line_start=5,
                category="style",
                severity="suggestion",
                title="Naming convention",
                description="Use snake_case",
            ),
        ],
        summary="Found 2 issues",
        tokens_used=200,
        processing_time_ms=1000.0,
        chunks_processed=2,
        files_reviewed=4,
        model_used="test-model",
    )


class TestGetFormatter:
    def test_rich_formatter(self):
        assert isinstance(get_formatter("rich"), RichFormatter)

    def test_json_formatter(self):
        assert isinstance(get_formatter("json"), JSONFormatter)

    def test_plain_formatter(self):
        assert isinstance(get_formatter("plain"), PlainFormatter)

    def test_unknown_defaults_to_rich(self):
        assert isinstance(get_formatter("unknown"), RichFormatter)


class TestSeverityStyles:
    def test_all_severities_defined(self):
        for sev in ["critical", "warning", "suggestion"]:
            assert sev in SEVERITY_STYLES
            style, label, icon = SEVERITY_STYLES[sev]
            assert style
            assert label
            assert icon


class TestCategoryIcons:
    def test_all_categories_defined(self):
        for cat in ["bug", "security", "performance", "style", "architecture"]:
            assert cat in CATEGORY_ICONS


class TestJSONFormatter:
    def test_empty_findings(self, empty_result, capsys):
        formatter = JSONFormatter()
        formatter.print_review(empty_result)
        output = json.loads(capsys.readouterr().out)

        assert output["findings"] == []
        assert output["stats"]["files_reviewed"] == 3
        assert output["stats"]["total_findings"] == 0
        assert output["stats"]["model_used"] == "test-model"

    def test_with_findings(self, result_with_findings, capsys):
        formatter = JSONFormatter()
        formatter.print_review(result_with_findings)
        output = json.loads(capsys.readouterr().out)

        assert len(output["findings"]) == 2
        assert output["findings"][0]["title"] == "Null reference"
        assert output["findings"][0]["severity"] == "critical"
        assert output["findings"][1]["title"] == "Naming convention"
        assert output["summary"] == "Found 2 issues"
        assert output["stats"]["total_findings"] == 2
        assert output["stats"]["tokens_used"] == 200

    def test_json_is_valid(self, result_with_findings, capsys):
        formatter = JSONFormatter()
        formatter.print_review(result_with_findings)
        raw = capsys.readouterr().out
        # Should not raise
        data = json.loads(raw)
        assert isinstance(data, dict)


class TestPlainFormatter:
    def test_empty_findings(self, empty_result, capsys):
        formatter = PlainFormatter()
        formatter.print_review(empty_result)
        output = capsys.readouterr().out

        assert "ARGUS CODE REVIEW" in output
        assert "No issues found" in output
        assert "test-model" in output

    def test_with_findings(self, result_with_findings, capsys):
        formatter = PlainFormatter()
        formatter.print_review(result_with_findings)
        output = capsys.readouterr().out

        assert "ARGUS CODE REVIEW" in output
        assert "Null reference" in output
        assert "Naming convention" in output
        assert "app/main.py:10" in output
        assert "critical" in output
        assert "suggestion" in output
        assert "SUMMARY" in output
        assert "2 issues" in output

    def test_severity_prefixes(self, capsys):
        for severity, (_, _, prefix) in SEVERITY_STYLES.items():
            result = ReviewResult(
                findings=[
                    AIFinding(
                        file_path="t.py",
                        line_start=1,
                        category="bug",
                        severity=severity,
                        title=f"Test {severity}",
                        description="desc",
                    )
                ],
                summary="",
                files_reviewed=1,
                model_used="m",
            )
            formatter = PlainFormatter()
            formatter.print_review(result)
            output = capsys.readouterr().out
            assert prefix in output

    def test_suggested_fix_shown(self, capsys):
        result = ReviewResult(
            findings=[
                AIFinding(
                    file_path="t.py",
                    line_start=1,
                    category="bug",
                    severity="warning",
                    title="Issue",
                    description="desc",
                    suggested_fix="Do this instead",
                )
            ],
            summary="",
            files_reviewed=1,
            model_used="m",
        )
        formatter = PlainFormatter()
        formatter.print_review(result)
        output = capsys.readouterr().out
        assert "Do this instead" in output


class TestRichFormatter:
    def test_empty_findings_no_crash(self, empty_result):
        """Rich formatter should not crash on empty findings."""
        formatter = RichFormatter()
        # Just verify it doesn't raise
        formatter.print_review(empty_result)

    def test_with_findings_no_crash(self, result_with_findings):
        """Rich formatter should not crash with findings."""
        formatter = RichFormatter()
        formatter.print_review(result_with_findings)
