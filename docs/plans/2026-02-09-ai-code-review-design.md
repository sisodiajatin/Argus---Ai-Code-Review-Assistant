# AI Code Review Bot - Design Document

**Date:** 2026-02-09
**Inspiration:** CodeRabbit
**Status:** Implementation Phase

## Overview

A GitHub-integrated bot that automatically reviews pull requests using LLM-powered analysis. It listens for PR events via webhooks, analyzes diffs with smart chunking, and posts intelligent review comments directly on GitHub.

## Core Flow

```
GitHub PR Event → Webhook → FastAPI Server → Diff Parser → Smart Chunker → LLM Analysis → GitHub Review Comments
```

## Tech Stack

- **Backend:** Python 3.11+ / FastAPI
- **AI:** OpenAI API (GPT-4) with structured prompts
- **Database:** SQLite (via SQLAlchemy)
- **GitHub Integration:** PyGithub + webhook handling
- **Async:** asyncio for concurrent PR processing
- **Config:** Pydantic settings, `.env` for secrets

## What the Bot Analyzes

- Code quality & best practices
- Potential bugs and logic errors
- Security vulnerabilities (SQL injection, XSS, hardcoded secrets, etc.)
- Architectural suggestions (design patterns, separation of concerns)
- Performance issues

## Future Enhancements (Not in v1)

- **Multi-VCS:** GitLab, Bitbucket support via VCSProvider interface
- **Fine-tuning:** Collect review data now, fine-tune custom model later
- **RAG:** Vector search for cross-file context understanding
- **Dashboard:** Web UI for metrics and configuration

## Components

### 1. Webhook Handler (`api/webhooks.py`)
- Receives GitHub PR events (opened, synchronize, reopened)
- Validates webhook signatures for security
- Queues the PR for processing

### 2. VCS Provider (`services/vcs/`)
- Abstract interface for version control operations
- GitHub implementation: fetch PR details, diffs, file contents, post review comments
- Clean abstraction for adding GitLab/Bitbucket later

### 3. Diff Parser (`services/diff_parser.py`)
- Parses unified diff format into structured file-level changes
- Extracts added/removed/modified lines with context
- Maps line numbers for accurate comment placement

### 4. Smart Chunker (`services/chunker.py`)
- Breaks large diffs into LLM-friendly chunks
- Groups related files together
- Summarizes unchanged files that provide context
- Respects token limits per LLM call

### 5. AI Analyzer (`services/analyzer.py`)
- Builds review prompts with diff context
- Calls OpenAI API with structured output parsing
- Categorizes findings: bug, security, performance, style, architecture
- Assigns severity levels: critical, warning, suggestion

### 6. Review Publisher (`services/publisher.py`)
- Maps AI findings back to specific file lines
- Posts inline review comments on the GitHub PR
- Creates a summary review comment with overview

### 7. Data Store (`models/`)
- Stores reviews, findings, repository configs
- Collects training data for future fine-tuning

## Data Models

### Repository
- id, github_id, full_name, webhook_secret
- default_config (JSON - review rules, ignored paths)
- created_at, updated_at

### PullRequest
- id, repo_id (FK), pr_number, title, author
- head_sha, base_sha, status (pending/reviewing/completed/failed)
- created_at, completed_at

### ReviewFinding
- id, pr_id (FK), file_path, line_number
- category (bug/security/performance/style/architecture)
- severity (critical/warning/suggestion)
- description, suggested_fix
- github_comment_id
- created_at

### ReviewSummary
- id, pr_id (FK)
- total_findings, critical_count, warning_count
- overall_assessment, summary_text
- tokens_used, model_used, processing_time_ms
- created_at

## Smart Chunking Strategy

1. **File prioritization** - Score files by risk: security-sensitive files rank higher
2. **Chunk by logical groups** - Keep related files together
3. **Context window management** - 30% for prompts, 70% for code context
4. **Diff-focused with surrounding context** - Diff + ~20 lines surrounding
5. **Multi-pass for large PRs** - Review in passes, generate unified summary
