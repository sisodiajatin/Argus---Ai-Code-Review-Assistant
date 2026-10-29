"""Convert Argus findings to SARIF 2.1.0.

SARIF is the standard format for static-analysis results. GitHub's
Security -> Code scanning tab and editors like VS Code display it.

Mapping:
- one rule per (category, severity), e.g. ``argus/security/critical``. GitHub
  reads a security result's severity from its rule's ``security-severity``
  property, so the severity has to be part of the rule.
- Argus severity -> SARIF level: critical=error, warning=warning,
  suggestion=note.
- ``partialFingerprints`` uses file + title (not the line), so a finding
  keeps its identity when code above it moves.
"""

import hashlib

from app import __version__
from app.models.schemas import AIFinding

SARIF_SCHEMA = "https://json.schemastore.org/sarif-2.1.0.json"
INFORMATION_URI = "https://github.com/sisodiajatin/Argus---Ai-Code-Review-Assistant"

LEVELS = {"critical": "error", "warning": "warning", "suggestion": "note"}
# GitHub maps security-severity to Critical (>=9), High (>=7), Medium (>=4), Low.
SECURITY_SEVERITY = {"critical": "9.0", "warning": "6.0", "suggestion": "3.0"}

CATEGORY_TEXT = {
    "bug": "Logic error, incorrect behavior or unhandled edge case",
    "security": "Security vulnerability or unsafe practice",
    "performance": "Inefficient code or scalability concern",
    "style": "Readability, naming or code-organization issue",
    "architecture": "Design, coupling or abstraction issue",
}


def _rule_id(finding: AIFinding) -> str:
    return f"argus/{finding.category}/{finding.severity}"


def _rule(category: str, severity: str) -> dict:
    # The category doubles as the tag; "security" is also what GitHub groups
    # security results by. SARIF requires tags to be unique.
    tags = [category]
    rule = {
        "id": f"argus/{category}/{severity}",
        "name": f"{category.capitalize()}{severity.capitalize()}",
        "shortDescription": {"text": f"{category.capitalize()} ({severity})"},
        "fullDescription": {"text": CATEGORY_TEXT.get(category, category)},
        "helpUri": INFORMATION_URI,
        "defaultConfiguration": {"level": LEVELS.get(severity, "note")},
        "properties": {"tags": tags, "precision": "medium"},
    }
    if category == "security":
        rule["properties"]["security-severity"] = SECURITY_SEVERITY.get(severity, "3.0")
    return rule


def _fingerprint(finding: AIFinding) -> str:
    key = f"{finding.file_path}|{finding.category}|{finding.title.strip().lower()}"
    return hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]


def _result(finding: AIFinding, rule_index: int) -> dict:
    start = finding.line_start or finding.line_end or 1
    end = max(start, finding.line_end or start)
    message = f"{finding.title}\n\n{finding.description}".strip()
    result = {
        "ruleId": _rule_id(finding),
        "ruleIndex": rule_index,
        "level": LEVELS.get(finding.severity, "note"),
        "message": {"text": message},
        "locations": [{
            "physicalLocation": {
                "artifactLocation": {
                    # removeprefix, not lstrip: ".github/x" must keep its dot
                    "uri": finding.file_path.removeprefix("./"),
                    "uriBaseId": "%SRCROOT%",
                },
                "region": {"startLine": start, "endLine": end},
            }
        }],
        "partialFingerprints": {"argusFinding/v1": _fingerprint(finding)},
    }
    if finding.suggested_fix:
        result["properties"] = {"suggestedFix": finding.suggested_fix}
    return result


def findings_to_sarif(findings: list[AIFinding], *, model: str = "") -> dict:
    """Build a SARIF 2.1.0 log for one Argus run."""
    rule_ids: list[str] = []
    rules: list[dict] = []
    results: list[dict] = []
    for finding in findings:
        rid = _rule_id(finding)
        if rid not in rule_ids:
            rule_ids.append(rid)
            rules.append(_rule(finding.category, finding.severity))
        results.append(_result(finding, rule_ids.index(rid)))

    driver = {
        "name": "Argus",
        "semanticVersion": __version__,
        "informationUri": INFORMATION_URI,
        "rules": rules,
    }
    run = {
        "tool": {"driver": driver},
        "results": results,
        "columnKind": "unicodeCodePoints",
        "originalUriBaseIds": {"%SRCROOT%": {"description": {"text": "Repository root"}}},
    }
    if model:
        run["properties"] = {"model": model}
    return {"$schema": SARIF_SCHEMA, "version": "2.1.0", "runs": [run]}
