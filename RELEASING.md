# Releasing Argus

Releases are published to PyPI by `.github/workflows/publish.yml` when a GitHub
release is published. The workflow re-runs the full CI suite, checks that the
release tag matches the code's version and that `CHANGELOG.md` has an entry,
then uploads to PyPI. A release can't ship if any of that fails.

## One-time setup

PyPI "trusted publishing" lets the workflow upload without an API token stored
in GitHub.

1. Sign in to [pypi.org](https://pypi.org), open **argus-ai-review** →
   **Manage** → **Publishing**, and add a GitHub publisher:

   | Field | Value |
   |-------|-------|
   | Owner | `sisodiajatin` |
   | Repository name | `Argus---Ai-Code-Review-Assistant` |
   | Workflow name | `publish.yml` |
   | Environment name | `pypi` |

2. In the GitHub repo, go to **Settings** → **Environments** → **New
   environment**, name it `pypi`. Optionally add yourself as a required
   reviewer so every upload waits for your approval.

3. If you created a PyPI API token for the 0.1.0 upload, revoke it once the
   first trusted release has worked.

## Each release

1. Update the version in `app/__init__.py` (`__version__`). Everything else
   (the package build, `argus --version`, `/api/health`) reads it from there.
2. In `CHANGELOG.md`, change `## [X.Y.Z] - Unreleased` to today's date and
   update the compare link at the bottom.
3. Merge to `main` and wait for CI to pass.
4. Create the release:

   ```bash
   gh release create vX.Y.Z --target main --title "vX.Y.Z" \
     --notes "See CHANGELOG.md for details."
   ```

   The tag must be `v` + the version (e.g. `v0.2.0`), or the workflow stops.
5. Watch **Actions** → **Publish to PyPI**. When it finishes, the package is
   on PyPI and the wheel and sdist are attached to the GitHub release.
6. Check it installs:

   ```bash
   pipx install --force "argus-ai-review==X.Y.Z" && argus --version
   ```
