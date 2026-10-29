"""Learn from reviewer feedback ("helpful" / "not helpful") on past findings.

Two layers, both scoped to a single repository:

1. Prompt hint: the model is told which kinds of findings this repo's
   reviewers rejected, so it avoids raising them again.
2. Deterministic filter: a new finding that closely matches a rejected one
   (same category, near-identical title) is removed even if the model
   raised it anyway, because prompt instructions alone aren't reliable.

Safety rules:
- Critical findings are never filtered, only hinted. One mis-click on
  "not helpful" must not hide a future SQL injection.
- If the same kind of finding was also marked helpful in this repo, it is
  not filtered (conflicting signals: let the model decide).
- Filtered findings are reported back to the caller so they can be shown,
  never silently dropped.
"""

import re
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.pull_request import PullRequest
from app.models.review import ReviewFinding
from app.models.schemas import AIFinding

# How many recent rated findings to learn from, per repository.
MAX_PATTERNS = 50
# How many rejected patterns to describe to the model (prompt budget).
MAX_PROMPT_PATTERNS = 15
# Title similarity (0..1) at which a new finding counts as "the same kind".
SIMILARITY_THRESHOLD = 0.6
# Severities the deterministic filter may remove.
FILTERABLE_SEVERITIES = {"warning", "suggestion"}

_STOPWORDS = {
    "a", "an", "the", "of", "in", "on", "for", "to", "and", "or", "with", "is",
    "are", "be", "by", "at", "as", "from", "this", "that", "it", "its", "via",
    "when", "not", "no", "missing", "potential", "possible",
}
_WORD_RE = re.compile(r"[a-z0-9_]+")


@dataclass(frozen=True)
class FeedbackPattern:
    """A past finding a reviewer rated, reduced to what we compare on."""

    category: str
    title: str
    note: str = ""


@dataclass
class FeedbackMemory:
    """Rated findings for one repository, most recent first."""

    rejected: list[FeedbackPattern] = field(default_factory=list)
    accepted: list[FeedbackPattern] = field(default_factory=list)

    @property
    def is_empty(self) -> bool:
        return not self.rejected


def _tokens(text: str) -> set[str]:
    words = _WORD_RE.findall(text.lower())
    # Light stemming so "credentials"/"credential" and "queries"/"query" match.
    stemmed = set()
    for w in words:
        if w in _STOPWORDS or len(w) < 3:
            continue
        if w.endswith("ies") and len(w) > 4:
            w = w[:-3] + "y"
        elif w.endswith("s") and not w.endswith("ss") and len(w) > 3:
            w = w[:-1]
        stemmed.add(w)
    return stemmed


def title_similarity(a: str, b: str) -> float:
    """Jaccard similarity of the meaningful words in two titles (0..1)."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return 1.0 if a.strip().lower() == b.strip().lower() else 0.0
    return len(ta & tb) / len(ta | tb)


def _matches(finding: AIFinding, pattern: FeedbackPattern) -> bool:
    return (
        finding.category == pattern.category
        and title_similarity(finding.title, pattern.title) >= SIMILARITY_THRESHOLD
    )


def apply_feedback(
    findings: list[AIFinding], memory: FeedbackMemory | None
) -> tuple[list[AIFinding], list[AIFinding]]:
    """Split findings into (kept, suppressed) using past feedback."""
    if memory is None or memory.is_empty:
        return findings, []

    kept: list[AIFinding] = []
    suppressed: list[AIFinding] = []
    for finding in findings:
        rejected = any(_matches(finding, p) for p in memory.rejected)
        accepted = any(_matches(finding, p) for p in memory.accepted)
        if rejected and not accepted and finding.severity in FILTERABLE_SEVERITIES:
            suppressed.append(finding)
        else:
            kept.append(finding)
    return kept, suppressed


def build_feedback_hint(memory: FeedbackMemory | None) -> str:
    """Plain-text list of rejected finding types for the review prompt."""
    if memory is None or memory.is_empty:
        return ""
    lines = []
    seen: set[tuple[str, str]] = set()
    for p in memory.rejected:
        key = (p.category, p.title.strip().lower())
        if key in seen:
            continue
        seen.add(key)
        line = f"- [{p.category}] {p.title.strip()}"
        if p.note:
            line += f" (reviewer note: {p.note.strip()[:200]})"
        lines.append(line)
        if len(lines) >= MAX_PROMPT_PATTERNS:
            break
    return "\n".join(lines)


async def load_feedback_memory(
    db: AsyncSession, repo_id: int, limit: int = MAX_PATTERNS
) -> FeedbackMemory:
    """Load the most recent rated findings for a repository."""
    rows = (
        await db.execute(
            select(
                ReviewFinding.category,
                ReviewFinding.title,
                ReviewFinding.feedback,
                ReviewFinding.feedback_note,
            )
            .join(PullRequest, PullRequest.id == ReviewFinding.pr_id)
            .where(
                PullRequest.repo_id == repo_id,
                ReviewFinding.feedback.in_(("helpful", "not_helpful")),
            )
            .order_by(ReviewFinding.feedback_at.desc(), ReviewFinding.id.desc())
            .limit(limit)
        )
    ).all()

    memory = FeedbackMemory()
    for category, title, feedback, note in rows:
        pattern = FeedbackPattern(category=category, title=title, note=note or "")
        (memory.rejected if feedback == "not_helpful" else memory.accepted).append(pattern)
    return memory
