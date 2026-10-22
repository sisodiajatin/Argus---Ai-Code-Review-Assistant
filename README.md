# Argus — The All-Seeing Code Reviewer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-184%20passing-brightgreen.svg)](#running-tests)
[![PyPI](https://img.shields.io/pypi/v/argus-ai-review.svg)](https://pypi.org/project/argus-ai-review/)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub Action](https://img.shields.io/badge/GitHub%20Action-available-purple.svg)](#github-action)

AI-powered code review that works everywhere — as a **GitHub webhook**, a **CLI tool**, and a **GitHub Action**. Uses any OpenAI-compatible LLM (Groq, Gemini, GPT-4, DeepSeek, Llama) to analyze diffs and post findings directly on pull requests.

<p align="center">
  <a href="docs/media/argus-launch.mp4">
    <img src="docs/media/argus-preview.gif" alt="Argus demo: the CLI finds a SQL injection and suggests a fix, the dashboard tracks the review, and the GitHub Action is three lines of YAML" width="100%">
  </a>
  <br>
  ▶ <a href="docs/media/argus-launch.mp4">Watch the full launch video with sound</a>
</p>

---

## Features

| Feature | Description |
|---------|-------------|
| **Bug Detection** | Logic errors, edge cases, null handling, race conditions |
| **Security Scanning** | SQL injection, XSS, hardcoded secrets, auth flaws |
| **Performance Analysis** | N+1 queries, memory leaks, blocking in async code |
| **Architecture Review** | SOLID principles, coupling, design patterns |
| **Language-Aware Prompts** | Tailored review hints for Python, JS/TS, Go, Rust, Java, C/C++, Ruby, PHP, Kotlin, Swift, and more |
| **PR Auto-Summarization** | Generates a plain-English "what this PR does" description |
| **Interactive TUI** | Rich terminal UI with progress animations |
| **Smart Chunking** | Prioritizes security-sensitive files, respects token limits |
| **Re-push Detection** | Edits existing comment instead of spamming new ones |
| **Commit Status Checks** | Sets pending/success/failure on commits |
| **Dashboard** | Web UI with analytics, settings, and re-review buttons |
| **GitHub Action** | Drop-in CI/CD integration for any repo |
| **Per-Repo Config** | `.argus.yaml` for project-specific settings |

---

## How It Works

```
Code Changes  -->  Diff Parser  -->  Smart Chunker  -->  AI Analyzer  -->  Results
                                                           |
                                              Language-specific prompts
                                              PR auto-summarization
```

**Three ways to use Argus:**

1. **CLI** — Run `argus` in any git repo for instant local reviews
2. **GitHub Webhook** — Auto-reviews every PR via a GitHub App
3. **GitHub Action** — Add to any repo's CI with 3 lines of YAML

---

## Quick Start

### Prerequisites

- Python 3.11+
- An API key from any OpenAI-compatible provider:
  - [Groq](https://console.groq.com/keys) (free tier, recommended)
  - [Google Gemini](https://aistudio.google.com/apikey) (free tier)
  - [DeepSeek](https://platform.deepseek.com/api_keys) (very cheap)
  - [OpenAI](https://platform.openai.com/api-keys) (paid)

### Install via pip (Recommended)

```bash
pip install argus-ai-review
```

Then configure your API key:

```bash
argus config set ai.api_key YOUR_API_KEY
argus config set ai.base_url https://api.groq.com/openai/v1
argus config set ai.model llama-3.3-70b-versatile
```

> **Windows users:** If `argus` is not recognized after install, you need to add Python's Scripts folder to your PATH. Run `python -c "import sysconfig; print(sysconfig.get_path('scripts'))"` to find the path, then add it to your system PATH environment variable and restart your terminal.

### Install from Source (For Development)

```bash
git clone https://github.com/sisodiajatin/Argus---Ai-Code-Review-Assistant.git
cd Argus---Ai-Code-Review-Assistant

python -m venv venv
source venv/bin/activate   # Linux/Mac
# or: venv\Scripts\activate  # Windows

pip install -e ".[dev]"     # CLI + server + test tools

# Set up your API key
argus config init
```

### Use the CLI

```bash
# Review all uncommitted changes (launches interactive TUI)
argus

# Compare current branch to main
argus review --base main

# Review only staged changes
argus review --type staged

# JSON output (for CI/scripting)
argus review --format json

# Override model
argus review --model gpt-4

# Skip files (repeatable or comma-separated; adds to .argus.yaml `ignore`)
argus review --ignore "docs/*,*.min.js"
```

**Exit codes** (useful in CI): `0` no critical findings · `1` critical findings ·
`2` the review could not be completed (e.g. invalid API key or provider outage).
A failed review never prints as a clean one.

### Run the Dashboard Server

```bash
# Local, single-user dashboard (no login)
DASHBOARD_AUTH_REQUIRED=false uvicorn app.main:app --host 127.0.0.1 --port 8000

# Or with Docker
docker-compose up -d
```

Open `http://localhost:8000` to see the dashboard.

> **Login is required by default.** Any deployment reachable by others needs GitHub OAuth
> (`GITHUB_CLIENT_ID`, `GITHUB_CLIENT_SECRET`) and an allowlist of GitHub usernames
> (`DASHBOARD_ALLOWED_USERS`). Signing in with GitHub alone does not grant access, because
> review findings quote code from your repositories. Only set
> `DASHBOARD_AUTH_REQUIRED=false` for a dashboard bound to localhost.

---

## GitHub Action

Add Argus to any repo with zero infrastructure:

```yaml
# .github/workflows/argus.yml
name: Argus Code Review
on:
  pull_request:
    types: [opened, synchronize]

jobs:
  review:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write   # needed to post the review comment
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: sisodiajatin/Argus---Ai-Code-Review-Assistant@main
        with:
          ai_api_key: ${{ secrets.AI_API_KEY }}
```

**Inputs:**

| Input | Default | Description |
|-------|---------|-------------|
| `ai_api_key` | (required) | API key for the AI provider |
| `ai_model` | `llama-3.3-70b-versatile` | Model name |
| `ai_base_url` | `https://api.groq.com/openai/v1` | Base URL |
| `base_branch` | (auto-detected) | Branch to compare against |
| `ignore_paths` | `""` | Comma-separated glob patterns |
| `fail_on_critical` | `true` | Fail the job when critical findings are reported |

The job also fails if the review itself can't complete (for example, an invalid API key),
so an AI provider outage is never mistaken for a clean review.

**Outputs:** `critical_count`, `total_findings`.

---

## Per-Repo Configuration

Create a `.argus.yaml` in your repo root:

```yaml
# AI model to use
model: llama-3.3-70b-versatile

# Default base branch
base_branch: main

# Default review type: all, staged, committed
review_type: all

# File patterns to ignore
ignore:
  - "*.lock"
  - "package-lock.json"
  - "node_modules/"
  - "dist/"
  - ".env"
```

Generate a starter config:

```bash
argus config init-repo
```

**Precedence:** CLI flags > `.argus.yaml` > `~/.codereview/.env` defaults

---

## GitHub Webhook Setup

For auto-reviewing every PR on push:

1. Create a [GitHub App](https://docs.github.com/en/apps/creating-github-apps) with:
   - **Permissions:** Pull Requests (Read & Write), Contents (Read), Commit Statuses (Read & Write)
   - **Events:** Pull request
2. Generate a private key and webhook secret
3. Configure `.env`:

```env
GITHUB_APP_ID=your_app_id
GITHUB_PRIVATE_KEY_PATH=./private-key.pem
GITHUB_WEBHOOK_SECRET=your_webhook_secret

AI_API_KEY=your_api_key
AI_MODEL=llama-3.3-70b-versatile
AI_BASE_URL=https://api.groq.com/openai/v1

PUBLIC_URL=https://your-domain.com
SESSION_SECRET=<python -c "import secrets; print(secrets.token_hex(32))">

# Dashboard login (OAuth App callback: https://your-domain.com/auth/github/callback)
GITHUB_CLIENT_ID=your_oauth_client_id
GITHUB_CLIENT_SECRET=your_oauth_client_secret
DASHBOARD_ALLOWED_USERS=your-github-username
```

4. Start the server and set the webhook URL to `https://your-domain.com/api/webhooks/github`

The server refuses to start without `AI_API_KEY`. If the AI provider fails during a review,
the commit status is set to **error** ("Review incomplete"), never to success.

---

## Docker Deployment

```bash
# Build and start
docker-compose up -d

# View logs
docker-compose logs -f argus

# Stop
docker-compose down
```

The Docker setup includes:
- Multi-stage build (Node for React dashboard + Python backend)
- Persistent SQLite volume at `/data`
- Health checks every 30s
- Auto-restart on failure

### Deploy to Railway

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

Set environment variables in the Railway dashboard.

### Deploy to Render

1. Connect your GitHub repo on [render.com](https://render.com)
2. Render auto-detects the `render.yaml` blueprint
3. Add environment variables in the Render dashboard

---

## Project Structure

```
argus/
├── app/                          # Server (FastAPI)
│   ├── main.py                   # Entry point + SPA routing
│   ├── config.py                 # Settings (Base/Server/CLI)
│   ├── api/
│   │   ├── webhooks.py           # GitHub webhook handler
│   │   ├── dashboard.py          # Dashboard REST API
│   │   ├── auth.py               # GitHub OAuth
│   │   └── pages.py              # SPA page routes
│   ├── models/
│   │   ├── database.py           # SQLAlchemy setup
│   │   ├── schemas.py            # Pydantic schemas
│   │   └── dashboard_schemas.py  # Dashboard API schemas
│   ├── services/
│   │   ├── review_pipeline.py    # Core orchestrator
│   │   ├── analyzer.py           # AI analysis + PR summarization
│   │   ├── chunker.py            # Smart chunking engine
│   │   ├── diff_parser.py        # Unified diff parser
│   │   ├── publisher.py          # GitHub comment publisher
│   │   └── vcs/
│   │       ├── base.py           # VCS provider interface
│   │       ├── github_provider.py  # GitHub API implementation
│   │       └── local_git.py      # Local git (for CLI)
│   └── prompts/
│       ├── system.py             # System prompt
│       ├── review.py             # Review + summary prompts
│       └── languages.py          # Language-specific hints
├── cli/                          # CLI tool
│   ├── main.py                   # Click commands
│   ├── tui.py                    # Interactive TUI
│   ├── formatters.py             # Rich/JSON/Plain output
│   ├── config_file.py            # .argus.yaml loader
│   └── db_sync.py                # Save CLI reviews to DB
├── dashboard/                    # React frontend
│   └── src/
│       ├── pages/                # Dashboard, Settings, ReviewDetail
│       ├── components/           # Sidebar, Charts
│       └── api/                  # API client
├── tests/                        # 184 tests
├── action.yml                    # GitHub Action definition
├── action_post_comment.py        # Action PR comment poster
├── Dockerfile                    # Multi-stage Docker build
├── docker-compose.yml            # One-command deployment
├── pyproject.toml                # Package config
└── requirements.txt              # Dependencies
```

---

## Running Tests

```bash
pip install -e ".[dev]"

# Lint
ruff check .

# All tests (no .env, network or dashboard build needed)
pytest tests/ -v

# Specific test file
pytest tests/test_language_hints.py -v

# With coverage
pytest tests/ -v --cov=app --cov=cli
```

---

## API Endpoints

### Webhook & Health

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Health check |
| `POST` | `/api/webhooks/github` | GitHub webhook receiver |

### Dashboard API

All dashboard endpoints require a logged-in, allowlisted user (HTTP 401 otherwise).

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/dashboard/stats` | Overview metrics |
| `GET` | `/api/dashboard/repos` | List repositories |
| `GET` | `/api/dashboard/repos/{id}/reviews` | List reviews for repo |
| `GET` | `/api/dashboard/reviews/{pr_id}` | Review detail with findings |
| `GET` | `/api/dashboard/analytics/trends` | Time-series analytics |
| `GET` | `/api/dashboard/analytics/categories` | Category breakdown |
| `GET` | `/api/dashboard/analytics/severity` | Severity breakdown |
| `GET` | `/api/dashboard/analytics/feedback` | Feedback stats |
| `POST` | `/api/dashboard/findings/{id}/feedback` | Mark a finding helpful / not helpful |
| `GET` | `/api/dashboard/settings` | Current settings (safe) |
| `POST` | `/api/dashboard/reviews/{id}/re-review` | Trigger re-review |

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/github/login` | Start GitHub OAuth |
| `GET` | `/auth/github/callback` | OAuth callback |
| `GET` | `/auth/logout` | Clear session |
| `GET` | `/auth/me` | Current user and whether login is required |

---

## Smart Chunking Strategy

Large PRs can't fit into a single LLM call. The smart chunker:

1. **Filters** — Removes lock files, binaries, generated code, ignored paths
2. **Prioritizes** — Security-sensitive files (auth, DB, API routes) reviewed first
3. **Groups** — Related files kept together (service + its test file)
4. **Token management** — Chunks respect the model's context window
5. **Multi-pass** — Large PRs reviewed in multiple passes with unified summary

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Backend | Python 3.11+ / FastAPI |
| AI | Any OpenAI-compatible LLM |
| Database | SQLite + SQLAlchemy (async) |
| CLI | Click + Rich |
| Frontend | React + TypeScript + Tailwind CSS |
| Deployment | Docker / Railway / Render |

---

## Cost

**$0** — Everything runs on free tiers:
- **AI**: Groq free tier (or Gemini free tier)
- **Database**: SQLite (no server needed)
- **Frontend**: React SPA served by FastAPI
- **Hosting**: Runs on your machine, or free tier on Railway/Render

---

## License

MIT
