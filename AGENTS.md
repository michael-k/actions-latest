# Agent Guide for actions-latest

## Project Overview

This is a personal fork of the [actions-latest](https://github.com/simonw/actions-latest) project by Simon Willison. It's a simple Python 3.12+ script that:

- Fetches all repos from the GitHub `actions` organization via the GitHub REST API
- Extracts exact `vX.Y.Z` semver tags from each repo and offers the latest that has been observed unchanged for at least 14 days (supply-chain quarantine)
- Writes results to `versions.txt` (one line per repo: `org/repo@vX.Y.Z`)
- Writes SHA-pinned results to `versions-sha.txt` (one line per repo: `org/repo@sha # vX.Y.Z`)
- Updates the README.md with the latest versions
- Records observed versions in `seen-versions.json` (the quarantine ledger) and caches repos with no version tags to avoid repeated API calls

**Note**: This is a personal fork. Contributions may not be considered or merged.

## Essential Commands

### Running Tests

```bash
python3 -m unittest test_fetch_versions -v
```

### Running the Main Script

```bash
python3 fetch_versions.py
```

To avoid GitHub API rate limits locally, set a `GITHUB_TOKEN` environment variable:

```bash
export GITHUB_TOKEN=ghp_your_token_here
python3 fetch_versions.py
# or if gh is available
GITHUB_TOKEN=$(gh auth token) python3 fetch_versions.py
```

## Code Organization

### Key Files

- **`fetch_versions.py`** - Main script

- **`test_fetch_versions.py`** - Unit tests

- **`versions.txt`** - Output file (auto-generated)
  - Format: one line per repo: `org/repo@vX.Y.Z`
  - Sorted alphabetically by repo name

- **`versions-sha.txt`** - SHA-pinned output file (auto-generated)
  - Format: one line per repo: `org/repo@commit-sha # vX.Y.Z`
  - Includes full commit SHA and semantic version tag
  - Sorted alphabetically by repo name

- **`unversioned.txt`** - Cache file (auto-generated)
  - List of repos known to have no version tags
  - Sorted alphabetically, one per line

- **`README.md`** - Documentation
  - Contains auto-updated versions section between `<!-- VERSIONS_START -->` and `<!-- VERSIONS_END -->` markers

- **`.github/workflows/update.yml`** - CI workflow
  - Runs on cron schedule and manual dispatch
  - Commits changes with message "chore: update versions"

## Code Conventions and Patterns

### Type Hints

- Python 3.12+ style: `set[str]`, `list[dict]`, `str | None`
- All functions have type hints for parameters and return types

### HTTP Requests

- **No external HTTP libraries** (no `requests`, `httpx`, etc.)
- Uses `subprocess.run` with `curl` to call GitHub API
- Optional Authorization header with `GITHUB_TOKEN` environment variable (higher rate limits)

### Caching Strategy

- `unversioned.txt` caches repos without version tags
- Reduces API calls on subsequent runs
- Cache is loaded at start and updated at end of run
- Sorted alphabetically before saving

### README Updates

- Uses regex to find and replace content between markers
- Pattern: `re.escape(README_START_MARKER) + r".*?" + re.escape(README_END_MARKER)` with `re.DOTALL`
- If markers don't exist, appends to end of README

## Modifying the Codebase

### Adding New Features

1. Write tests in `test_fetch_versions.py` following existing patterns
2. Implement in `fetch_versions.py` with type hints
3. Use standard library only (no new dependencies)
4. Run tests locally before committing

### Testing Changes

Always run: `python3 -m unittest test_fetch_versions -v`
