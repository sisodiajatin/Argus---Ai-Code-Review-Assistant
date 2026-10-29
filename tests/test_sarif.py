"""SARIF 2.1.0 output, validated against the official OASIS schema."""

import json
import subprocess
from pathlib import Path
from unittest.mock import AsyncMock, patch

import jsonschema
import pytest
from click.testing import CliRunner

from app.models.schemas import AIFinding
from app.services.analyzer import AIAnalyzer, ChunkAnalysisError
from app.services.sarif import findings_to_sarif

SCHEMA = json.loads((Path(__file__).parent / "fixtures" / "sarif-schema-2.1.0.json").read_text())


def validate(log: dict) -> None:
    jsonschema.Draft4Validator(SCHEMA).validate(log)


def f(title="SQL injection", category="security", severity="critical", path="app/db.py",
      line=10, end=None, fix=None):
    return AIFinding(file_path=path, line_start=line, line_end=end or line, category=category,
                     severity=severity, title=title, description="Explain why.", suggested_fix=fix)


class TestSarifLog:
    def test_valid_against_official_schema(self):
        log = findings_to_sarif([
            f(),
            f("Division by zero", "bug", "warning", "calc.py", 3, 5, fix="if not xs: return 0"),
            f("Naming", "style", "suggestion", "util.py", None),
        ], model="openai/gpt-oss-120b")
        validate(log)
        assert log["version"] == "2.1.0"

    def test_empty_run_is_valid(self):
        log = findings_to_sarif([])
        validate(log)
        assert log["runs"][0]["results"] == []

    def test_severity_maps_to_level(self):
        results = findings_to_sarif([
            f(severity="critical"), f("b", severity="warning"), f("c", severity="suggestion"),
        ])["runs"][0]["results"]
        assert [r["level"] for r in results] == ["error", "warning", "note"]

    def test_security_rules_carry_security_severity(self):
        rules = findings_to_sarif([f(severity="critical"), f("x", "bug", "warning")])["runs"][0]["tool"]["driver"]["rules"]
        security = next(r for r in rules if r["id"] == "argus/security/critical")
        bug = next(r for r in rules if r["id"] == "argus/bug/warning")
        assert security["properties"]["security-severity"] == "9.0"
        assert "security" in security["properties"]["tags"]
        assert "security-severity" not in bug["properties"]

    def test_rules_are_unique_and_rule_index_points_at_them(self):
        log = findings_to_sarif([f("a"), f("b"), f("c", "bug", "warning")])
        run = log["runs"][0]
        ids = [r["id"] for r in run["tool"]["driver"]["rules"]]
        assert ids == ["argus/security/critical", "argus/bug/warning"]
        for result in run["results"]:
            assert ids[result["ruleIndex"]] == result["ruleId"]

    def test_location_and_region(self):
        result = findings_to_sarif([f(line=3, end=5)])["runs"][0]["results"][0]
        loc = result["locations"][0]["physicalLocation"]
        assert loc["artifactLocation"] == {"uri": "app/db.py", "uriBaseId": "%SRCROOT%"}
        assert loc["region"] == {"startLine": 3, "endLine": 5}

    def test_missing_line_defaults_to_line_one(self):
        region = findings_to_sarif([f(line=None)])["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["region"]
        assert region == {"startLine": 1, "endLine": 1}

    @pytest.mark.parametrize("path,expected", [
        ("./src/a.py", "src/a.py"),
        (".github/workflows/ci.yml", ".github/workflows/ci.yml"),  # lstrip("./") would break this
    ])
    def test_uri_keeps_dotfiles(self, path, expected):
        uri = findings_to_sarif([f(path=path)])["runs"][0]["results"][0]["locations"][0]["physicalLocation"]["artifactLocation"]["uri"]
        assert uri == expected

    def test_fingerprint_survives_line_moves(self):
        a = findings_to_sarif([f(line=10)])["runs"][0]["results"][0]["partialFingerprints"]
        b = findings_to_sarif([f(line=42)])["runs"][0]["results"][0]["partialFingerprints"]
        c = findings_to_sarif([f(title="Other")])["runs"][0]["results"][0]["partialFingerprints"]
        assert a == b and a != c

    def test_suggested_fix_is_kept(self):
        result = findings_to_sarif([f(fix="use params")])["runs"][0]["results"][0]
        assert result["properties"]["suggestedFix"] == "use params"


@pytest.fixture
def repo(tmp_path):
    def git(*args):
        subprocess.run(["git", *args], cwd=tmp_path, check=True, capture_output=True)
    git("init", "-q", "-b", "main")
    git("config", "user.email", "t@example.com")
    git("config", "user.name", "t")
    (tmp_path / "a.py").write_text("x = 1\n")
    git("add", ".")
    git("commit", "-qm", "init")
    (tmp_path / "a.py").write_text("import pickle\npickle.loads(data)\n")
    git("add", "a.py")
    return tmp_path


def run_cli(repo, monkeypatch, *extra, findings=None, error=None):
    from cli.main import cli
    from app.services.review_pipeline import ReviewPipeline, ReviewResult

    monkeypatch.setenv("AI_API_KEY", "sk-test")
    if error:
        ctx = patch.object(AIAnalyzer, "analyze_chunk", new=AsyncMock(side_effect=error))
    else:
        async def fake_run(self, **kwargs):
            return ReviewResult(findings=findings or [], model_used="m")
        ctx = patch.object(ReviewPipeline, "run", new=fake_run)
    with ctx, patch.object(AIAnalyzer, "generate_pr_summary_with_usage",
                           new=AsyncMock(return_value=("", 0))):
        return CliRunner().invoke(cli, ["review", "-p", str(repo), "-t", "staged", *extra])


class TestCli:
    def test_sarif_flag_writes_valid_file_next_to_json(self, repo, monkeypatch, tmp_path):
        out = tmp_path / "out.sarif"
        result = run_cli(repo, monkeypatch, "-f", "json", "--sarif", str(out), findings=[f(path="a.py")])
        assert result.exit_code == 1  # critical finding
        json.loads(result.output)  # stdout is still the JSON report
        log = json.loads(out.read_text())
        validate(log)
        assert log["runs"][0]["results"][0]["ruleId"] == "argus/security/critical"

    def test_format_sarif_prints_sarif(self, repo, monkeypatch):
        result = run_cli(repo, monkeypatch, "-f", "sarif", findings=[f("Naming", "style", "suggestion")])
        assert result.exit_code == 0
        validate(json.loads(result.output))

    def test_failed_review_writes_no_sarif(self, repo, monkeypatch, tmp_path):
        out = tmp_path / "out.sarif"
        result = run_cli(repo, monkeypatch, "-f", "json", "--sarif", str(out),
                         error=ChunkAnalysisError("c0", ConnectionError("down")))
        assert result.exit_code == 2
        assert not out.exists()  # a failed review must never look like a clean scan

    def test_no_changes_writes_empty_sarif(self, tmp_path, monkeypatch):
        from cli.main import cli
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=tmp_path, check=True)
        monkeypatch.setenv("AI_API_KEY", "sk-test")
        out = tmp_path / "out.sarif"
        result = CliRunner().invoke(cli, ["review", "-p", str(tmp_path), "-t", "staged",
                                          "-f", "sarif", "--sarif", str(out)])
        assert result.exit_code == 0
        validate(json.loads(result.output))
        validate(json.loads(out.read_text()))
