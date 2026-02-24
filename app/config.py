"""Application configuration using Pydantic settings.

Layered settings architecture:
- BaseAppSettings: Shared settings for AI, DB, and review (used by CLI + server)
- ServerSettings: Adds GitHub App, OAuth, and hosting settings (server only)
- CLISettings: Adds output preferences (CLI only)
"""

from pathlib import Path

from pydantic_settings import BaseSettings
from pydantic import Field

# Global config directory: ~/.codereview/.env
_GLOBAL_ENV = str(Path.home() / ".codereview" / ".env")

# Shared database path — always stored in ~/.codereview/ so CLI and dashboard use the same DB
_DEFAULT_DB = f"sqlite+aiosqlite:///{Path.home() / '.codereview' / 'codereview.db'}"


class BaseAppSettings(BaseSettings):
    """Settings shared by both server and CLI."""

    # AI Provider Configuration (any OpenAI-compatible API)
    ai_api_key: str = Field(default="", description="API key for the AI provider")
    ai_model: str = Field(default="gemini-2.0-flash", description="Model to use for code review")
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

    # Application
    app_host: str = Field(default="0.0.0.0", description="Application host")
    app_port: int = Field(default=8000, description="Application port")


class CLISettings(BaseAppSettings):
    """Settings for the CLI tool."""

    output_format: str = Field(default="rich", description="Output format: rich, json, plain")


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
