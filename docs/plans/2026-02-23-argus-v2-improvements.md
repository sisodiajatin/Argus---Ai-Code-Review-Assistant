# Argus v2 — Improvements & New Features Design

**Date:** 2026-02-23
**Status:** Approved

## Overview

Three phases of improvements to make Argus a portfolio-ready, production-grade code review tool.

---

## Phase 1a: GitHub Webhook Flow Improvements

### GitHub Commit Status Checks
- On webhook receive: set **pending** status check on commit → "Argus: Reviewing..."
- On review complete: update to **success/failure** → "Argus: 2 critical, 3 warnings" or "Argus: No issues found"
- Uses GitHub Checks API via `github_provider.py`

### Improved PR Summary Comment
- Formatted markdown table with severity counts
- Top findings listed with file links
- "Reviewed by Argus" footer with processing time
- On re-push (synchronize): **edit existing comment** instead of posting new one

**Files:** `app/services/publisher.py`, `app/services/vcs/github_provider.py`, `app/api/webhooks.py`

---

## Phase 1b: Dashboard Improvements

### Settings Page (`/settings`)
- AI config display (model, base URL — read-only)
- Webhook URL display for copy-paste
- Ignored paths editor (glob patterns)
- New `settings` DB table

### Re-Review Button
- Button on `ReviewDetail` page
- `POST /api/reviews/{pr_id}/re-review` endpoint
- Re-fetches files from GitHub, runs pipeline again
- Disabled for CLI-based reviews

### Real-time Review Status
- Polling on `ReviewDetail` page every 3s while status is `REVIEWING`
- Animated progress indicator
- Auto-refresh on `COMPLETED`

**Files:** `dashboard/src/pages/Settings.tsx`, `app/api/dashboard.py`, `app/models/settings.py`, `dashboard/src/pages/ReviewDetail.tsx`

---

## Phase 1c: CLI Improvements

### `.argus.yaml` Config File
```yaml
model: llama-3.3-70b-versatile
base_branch: main
review_type: staged
ignore:
  - "*.lock"
  - "node_modules/"
  - "dist/"
```
- Auto-read from repo root
- CLI flags override yaml values
- `argus config init` generates starter file

### GitHub Action (`action.yml`)
```yaml
- uses: sisodiajatin/argus@main
  with:
    ai_api_key: ${{ secrets.AI_API_KEY }}
    ai_model: llama-3.3-70b-versatile
    ai_base_url: https://api.groq.com/openai/v1
```
- Installs Argus, runs review, posts PR comments
- Free alternative to CodeRabbit

**Files:** `cli/main.py`, `cli/config_file.py`, `action.yml`, `.github/workflows/argus-action.yml`

---

## Phase 2: New Features

### PR Auto-Summarization
- Generate plain-English summary of what the PR does
- Posted as first comment before findings
- "This PR adds user authentication using JWT tokens, modifies 3 files..."

### Language-Specific Prompts
- Tailored prompts for Python, JavaScript, TypeScript, Go, Rust
- Better findings based on language idioms and common patterns

**Files:** `app/services/analyzer.py`, `app/prompts/`

---

## Phase 3: Deployment

### Cloud Deployment
- Railway or Render (free tier, one-click deploy)
- Docker image already ready
- Just connect GitHub repo and set env vars

### Portfolio Polish
- Custom domain (optional)
- README badges: deploy button, Docker, test count
- Demo GIF/video

**Files:** `README.md`, `railway.json` or `render.yaml`

---

## Implementation Order

| Step | Task | Effort |
|------|------|--------|
| 1a | GitHub status checks + improved PR comments | Small |
| 1b | Dashboard: settings, re-review, live status | Medium |
| 1c | CLI: .argus.yaml + GitHub Action | Medium |
| 2 | PR summarization + language prompts | Small |
| 3 | Deploy + README polish | Small |
