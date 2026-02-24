# Argus — The All-Seeing Code Reviewer

[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![Tests](https://img.shields.io/badge/tests-160%20passing-brightgreen.svg)](#running-tests)
[![License: MIT](https://img.shields.io/badge/license-MIT-green.svg)](LICENSE)
[![GitHub Action](https://img.shields.io/badge/GitHub%20Action-available-purple.svg)](#github-action)

AI-powered code review that works everywhere — as a **GitHub webhook**, a **CLI tool**, and a **GitHub Action**. Uses any OpenAI-compatible LLM (Groq, Gemini, GPT-4, DeepSeek, Llama) to analyze diffs and post findings directly on pull requests.

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

### Install & Configure

```bash
git clone https://github.com/sisodiajatin/argus.git
cd argus

python -m venv venv
source venv/bin/activate   # Linux/Mac
# or: venv\Scripts\activate  # Windows

pip install -r requirements.txt
pip install -e .

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
```

### Run the Dashboard Server

```bash
# Start the server
uvicorn app.main:app --reload --port 8000

# Or with Docker
docker-compose up -d
```

Open `http://localhost:8000` to see the dashboard.

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
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
      - uses: sisodiajatin/argus@main
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
```

4. Start the server and set the webhook URL to `https://your-domain.com/api/webhooks/github`

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
├── tests/                        # 160 tests
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
# All tests
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

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/dashboard/stats` | Overview metrics |
| `GET` | `/api/dashboard/repos` | List repositories |
| `GET` | `/api/dashboard/repos/{id}/reviews` | List reviews for repo |
| `GET` | `/api/dashboard/reviews/{pr_id}` | Review detail with findings |
| `GET` | `/api/dashboard/analytics/trends` | Time-series analytics |
| `GET` | `/api/dashboard/analytics/categories` | Category breakdown |
| `GET` | `/api/dashboard/settings` | Current settings (safe) |
| `POST` | `/api/dashboard/reviews/{id}/re-review` | Trigger re-review |

### Auth

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/auth/github/login` | Start GitHub OAuth |
| `GET` | `/auth/github/callback` | OAuth callback |
| `POST` | `/auth/logout` | Clear session |

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
