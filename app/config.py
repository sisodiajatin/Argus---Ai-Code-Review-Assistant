"""Application configuration using Pydantic settings.

Layered settings architecture:
- BaseAppSettings: Shared settings for AI, DB, and review (used by CLI + server)
- ServerSettings: Adds GitHub App, OAuth, and hosting settings (server only)
- CLISettings: Adds output preferences (CLI only)
"""

import hashlib
from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import AliasChoices, Field

# Global config directory: ~/.codereview/.env
_GLOBAL_ENV = str(Path.home() / ".codereview" / ".env")

# Shared database path — always stored in ~/.codereview/ so CLI and dashboard use the same DB
_DEFAULT_DB = f"sqlite+aiosqlite:///{Path.home() / '.codereview' / 'codereview.db'}"


class BaseAppSettings(BaseSettings):
    """Settings shared by both server and CLI."""

    # AI Provider Configuration (any OpenAI-compatible API)
    ai_api_key: str = Field(default="", description="API key for the AI provider")
    ai_model: str = Field(default="gemini-3.8-flash", description="Model to use for code review")
    ai_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta/openai/",
        description="Base URL for the OpenAI-compatible API",
    )

    # Database — stored in ~/.codereview/ so CLI and dashboard share the same DB
    database_url: str = Field(
        default=_DEFAULT_DB,
        description="Database connection URL",
    )

    # Logging
    log_level: str = Field(default="info", description="Logging level")

    # Review settings
    max_files_per_review: int = Field(default=50, description="Maximum files to review per PR")
    max_diff_lines: int = Field(default=5000, description="Maximum diff lines to process")
    context_lines: int = Field(default=20, description="Lines of context around diff changes")
    chunk_token_limit: int = Field(default=6000, description="Max tokens per LLM chunk")

    # Review filtering — applied post-analysis to remove unwanted findings
    review_focus: list[str] = Field(
        default_factory=list,
        description="Only keep findings in these categories (empty = all). Options: bug, security, performance, style, architecture",
    )
    severity_threshold: str = Field(
        default="suggestion",
        description="Minimum severity to report. Options: critical, warning, suggestion",
    )

    # Searches: .env (current dir) → ~/.codereview/.env (global)
    model_config = {
        "env_file": (".env", _GLOBAL_ENV),
        "env_file_encoding": "utf-8",
        "extra": "ignore",
    }


class ServerSettings(BaseAppSettings):
    """Additional settings for the webhook server and dashboard."""

    # GitHub App Configuration
    github_app_id: str = Field(description="GitHub App ID")
    github_private_key_path: str = Field(
        default="./private-key.pem",
        description="Path to GitHub App private key PEM file",
    )
    github_private_key: str = Field(
        default="",
        description="GitHub App private key PEM content (alternative to file path, for cloud deployment)",
    )
    github_webhook_secret: str = Field(description="GitHub webhook secret for signature verification")

    # GitHub OAuth (dashboard login). Reads GITHUB_CLIENT_ID / GITHUB_CLIENT_SECRET,
    # the names documented in .env.example, as well as the longer OAuth-prefixed names.
    github_oauth_client_id: str = Field(
        default="",
        validation_alias=AliasChoices("GITHUB_CLIENT_ID", "GITHUB_OAUTH_CLIENT_ID"),
        description="GitHub OAuth App client ID (dashboard login)",
    )
    github_oauth_client_secret: str = Field(
        default="",
        validation_alias=AliasChoices("GITHUB_CLIENT_SECRET", "GITHUB_OAUTH_CLIENT_SECRET"),
        description="GitHub OAuth App client secret (dashboard login)",
    )

    # Dashboard security
    session_secret: str = Field(
        default="",
        description="Secret for signing dashboard session cookies. "
        "If unset, a key is derived from the webhook secret (set this explicitly in production).",
    )
    dashboard_auth_required: bool = Field(
        default=True,
        description="Require GitHub login for the dashboard API. "
        "Set to false only for a local, single-user dashboard.",
    )
    dashboard_allowed_users: str = Field(
        default="",
        description="Comma-separated GitHub usernames allowed to log in to the dashboard. "
        "Empty = nobody (GitHub login alone does not grant access).",
    )
    frontend_url: str = Field(
        default="",
        description="Origin of a separately hosted dashboard (e.g. https://argus.vercel.app). "
        "Allowed for CORS and used for post-login redirects.",
    )

    # Incremental review: on a new push, re-review only files changed since the
    # last completed review and carry forward findings for the rest.
    incremental_review: bool = Field(default=True, description="Review only files changed since the last review")

    # Application
    app_host: str = Field(default="0.0.0.0", description="Application host")
    app_port: int = Field(default=8000, description="Application port")
    public_url: str = Field(
        default="",
        description="Public base URL of this server (used to show the webhook URL)",
    )

    @property
    def dashboard_allowed_user_set(self) -> set[str]:
        return {u.strip().lower() for u in self.dashboard_allowed_users.split(",") if u.strip()}

    @property
    def effective_session_secret(self) -> str:
        """Session signing key, kept separate from the webhook secret."""
        if self.session_secret:
            return self.session_secret
        # Domain-separated derivation so the cookie key is never the raw webhook secret.
        return hashlib.sha256(
            f"argus-session:{self.github_webhook_secret}".encode("utf-8")
        ).hexdigest()


class CLISettings(BaseAppSettings):
    """Settings for the CLI tool."""

    output_format: str = Field(default="rich", description="Output format: rich, json, plain")


def ensure_sqlite_dir(database_url: str) -> None:
    """Create the parent directory of a file-based SQLite database if missing."""
    prefix = "sqlite+aiosqlite:///"
    if not database_url.startswith(prefix):
        return
    db_path = database_url[len(prefix):]
    if not db_path or db_path == ":memory:":
        return
    Path(db_path).expanduser().parent.mkdir(parents=True, exist_ok=True)


# Backward-compatible aliases
Settings = ServerSettings


def get_settings() -> ServerSettings:
    """Get server settings instance (backward compatible)."""
    return ServerSettings()


def get_base_settings() -> BaseAppSettings:
    """Get base settings (works without GitHub App credentials)."""
    return BaseAppSettings()


def get_cli_settings() -> CLISettings:
    """Get CLI-specific settings."""
    return CLISettings()
