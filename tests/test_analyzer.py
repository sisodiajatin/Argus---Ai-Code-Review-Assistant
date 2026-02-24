"""Tests for the AI analyzer service."""

import json

import pytest

from app.services.analyzer import AIAnalyzer


class TestResponseParsing:
    """Test the response parsing logic without hitting the OpenAI API."""

    def test_parse_valid_findings(self):
        response_text = json.dumps({
            "findings": [
                {
                    "file_path": "app/main.py",
                    "line_start": 10,
                    "line_end": 10,
                    "category": "security",
                    "severity": "critical",
                    "title": "Hardcoded secret",
                    "description": "API key is hardcoded in source",
                    "suggested_fix": "Use environment variables",
                }
            ],
            "summary": "Found a security issue",
        })

        analyzer = AIAnalyzer.__new__(AIAnalyzer)
        findings = analyzer._parse_findings(response_text)

        assert len(findings) == 1
        assert findings[0].file_path == "app/main.py"
        assert findings[0].category == "security"
        assert findings[0].severity == "critical"

    def test_parse_empty_findings(self):
        response_text = json.dumps({"findings": [], "summary": "All good"})

        analyzer = AIAnalyzer.__new__(AIAnalyzer)
        findings = analyzer._parse_findings(response_text)

        assert len(findings) == 0

    def test_parse_invalid_json(self):
        analyzer = AIAnalyzer.__new__(AIAnalyzer)
        findings = analyzer._parse_findings("not valid json at all")

        assert len(findings) == 0

    def test_parse_json_in_code_block(self):
        response_text = """Here are my findings:
```json
{
    "findings": [
        {
            "file_path": "test.py",
            "line_start": 5,
            "category": "bug",
            "severity": "warning",
            "title": "Off by one",
            "description": "Loop index issue"
        }
    ],
    "summary": "Minor issue"
}
```"""
        analyzer = AIAnalyzer.__new__(AIAnalyzer)
        findings = analyzer._parse_findings(response_text)

        assert len(findings) == 1
        assert findings[0].category == "bug"

    def test_validate_category_valid(self):
        assert AIAnalyzer._validate_category("bug") == "bug"
        assert AIAnalyzer._validate_category("security") == "security"
        assert AIAnalyzer._validate_category("PERFORMANCE") == "performance"

    def test_validate_category_invalid(self):
        assert AIAnalyzer._validate_category("unknown") == "style"
        assert AIAnalyzer._validate_category("") == "style"

    def test_validate_severity_valid(self):
        assert AIAnalyzer._validate_severity("critical") == "critical"
        assert AIAnalyzer._validate_severity("WARNING") == "warning"
        assert AIAnalyzer._validate_severity("suggestion") == "suggestion"

    def test_validate_severity_invalid(self):
        assert AIAnalyzer._validate_severity("high") == "suggestion"
        assert AIAnalyzer._validate_severity("") == "suggestion"

    def test_build_fallback_summary(self):
        from app.models.schemas import AIFinding

        findings = [
            AIFinding(
                file_path="test.py",
                line_start=1,
                category="security",
                severity="critical",
                title="Critical issue",
                description="Something bad",
            ),
            AIFinding(
                file_path="test2.py",
                line_start=5,
                category="style",
                severity="suggestion",
                title="Style issue",
                description="Could be better",
            ),
        ]

        summary = AIAnalyzer._build_fallback_summary(findings)

        assert "2" in summary  # total findings
        assert "critical" in summary.lower()
        assert "Critical issue" in summary
