"""Load .argus.yaml config from a repo root.

Precedence: CLI flags > .argus.yaml > global ~/.codereview/.env defaults
"""

import logging
from pathlib import Path
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)

STARTER_YAML = """\
# Argus — Code Review Configuration
# Place this file in your repo root. CLI flags override these values.

# AI model to use for review
# model: llama-3.3-70b-versatile

# Base branch to compare against (for --type committed)
# base_branch: main

# Default review type: all, staged, committed
# review_type: all

# File patterns to ignore during review
ignore:
  - "*.lock"
  - "package-lock.json"
  - "node_modules/"
  - "dist/"
  - ".env"

# Review focus — only report findings in these categories.
# Options: bug, security, performance, style, architecture
# Leave commented out to include all categories.
# focus:
#   - security
#   - bug
#   - performance

# Minimum severity threshold — hide findings below this level.
# Options: critical, warning, suggestion (default: suggestion — show everything)
# severity_threshold: warning
"""

# Ordered from highest to lowest severity
SEVERITY_ORDER = {"critical": 2, "warning": 1, "suggestion": 0}
VALID_CATEGORIES = {"bug", "security", "performance", "style", "architecture"}


@dataclass
class RepoConfig:
    """Configuration loaded from .argus.yaml."""
    model: str | None = None
    base_branch: str | None = None
    review_type: str | None = None
    ignore: list[str] = field(default_factory=list)
    focus: list[str] = field(default_factory=list)
    severity_threshold: str | None = None


def load_repo_config(repo_path: str = ".") -> RepoConfig:
    """Load .argus.yaml from the given repo path, if it exists."""
    config_path = Path(repo_path) / ".argus.yaml"
    if not config_path.is_file():
        # Also check .argus.yml
        config_path = Path(repo_path) / ".argus.yml"
        if not config_path.is_file():
            return RepoConfig()

    try:
        # Use a simple YAML parser to avoid adding pyyaml dependency
        return _parse_yaml(config_path.read_text(encoding="utf-8"))
    except Exception as e:
        logger.warning(f"Failed to parse {config_path}: {e}")
        return RepoConfig()


def _parse_yaml(text: str) -> RepoConfig:
    """Minimal YAML parser for our simple config format.

    Handles: key: value pairs and key: [list items with - prefix].
    No dependency on pyyaml.
    """
    config = RepoConfig()
    current_list_key: str | None = None
    current_list: list[str] = []

    for line in text.splitlines():
        stripped = line.strip()

        # Skip comments and empty lines
        if not stripped or stripped.startswith("#"):
            continue

        # List item (indented with -)
        if stripped.startswith("- "):
            if current_list_key:
                value = stripped[2:].strip().strip('"').strip("'")
                current_list.append(value)
            continue

        # Key-value pair
        if ":" in stripped:
            # Flush previous list
            if current_list_key and current_list:
                setattr(config, current_list_key, current_list)
                current_list = []
                current_list_key = None

            key, _, value = stripped.partition(":")
            key = key.strip()
            value = value.strip().strip('"').strip("'")

            if not value:
                # This is a list key (next lines will have - items)
                if hasattr(config, key):
                    current_list_key = key
                    current_list = []
            else:
                if hasattr(config, key):
                    setattr(config, key, value)

    # Flush final list
    if current_list_key and current_list:
        setattr(config, current_list_key, current_list)

    return config


def create_starter_config(repo_path: str = ".") -> Path:
    """Create a starter .argus.yaml in the given repo."""
    config_path = Path(repo_path) / ".argus.yaml"
    config_path.write_text(STARTER_YAML, encoding="utf-8")
    return config_path
