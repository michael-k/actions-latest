#!/usr/bin/env python3
"""
Fetch all repos from the GitHub actions organization and their tags via the API,
and generate a versions.txt file with the latest vINTEGER tags.

No git cloning required - uses GitHub REST API only.

Repos known to have no vINTEGER tags are cached in unversioned.txt to skip
API calls on future runs.
"""

import json
import os
import re
import subprocess
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


# Base URL with fallback
BASE_URL = "https://michael-k.github.io/quarantined-actions/"

# Markers for the README section
README_START_MARKER = "<!-- VERSIONS_START -->"
README_END_MARKER = "<!-- VERSIONS_END -->"
README_SHA_START_MARKER = "<!-- VERSIONS_SHA_START -->"
README_SHA_END_MARKER = "<!-- VERSIONS_SHA_END -->"
ORG_NAME = "actions"
ADDITIONAL_REPOS: list[str] = []

# Org bundles: each gets its own *-versions.txt and index.json entry (like the
# default bundle). "full" lists every repo in the org; "search" narrows via a
# GitHub search query, for orgs that also contain many non-action repos. In both
# modes only repos with a root action.yml/action.yaml are kept (see
# is_action_repo), so no per-org exclude list is needed.
ORG_BUNDLES: dict[str, dict] = {
    "aws-actions": {"source": "full"},
    "astral-sh": {"source": "full"},
    "google-github-actions": {"source": "full"},
    "docker": {"source": "search", "query": "org:docker topic:github-actions"},
    "hashicorp": {"source": "search", "query": "org:hashicorp topic:github-actions"},
    "Azure": {"source": "search", "query": "org:Azure topic:github-actions"},
    "pnpm": {"source": "search", "query": "org:pnpm topic:github-actions"},
    "webfactory": {"source": "search", "query": "org:webfactory topic:github-actions"},
}
ADDITIONAL_ORGS: list[str] = list(ORG_BUNDLES)
SKIP_REPOS: list[str] = [
    "action-versions",
    "actions-runner-controller",
    "actions-sync",
    "alpine_nodejs",
    "container-prebuilt-action",
    "gh-actions-cache",
    "github",
    "publish-action",
    "publish-immutable-action",
    "runner",
    "runner-container-hooks",
]
GITHUB_API_URL = "https://api.github.com"

# Minimum age, in days, before an observed version is offered to consumers.
QUARANTINE_DAYS = 14

# first_seen value used to grandfather versions already published before the
# ledger existed, so they remain available without a 14-day blackout.
GRANDFATHER_DATE = date(2000, 1, 1)


SCRIPT_DIR = Path(__file__).parent.resolve()


def get_versions_file() -> Path:
    return SCRIPT_DIR / "versions.txt"


def get_versions_sha_file() -> Path:
    return SCRIPT_DIR / "versions-sha.txt"


def get_unversioned_file() -> Path:
    return SCRIPT_DIR / "unversioned.txt"


def get_org_versions_file(org: str) -> Path:
    """Get the versions file path for a specific org."""
    return SCRIPT_DIR / f"{org.lower()}-versions.txt"


def get_org_versions_sha_file(org: str) -> Path:
    """Get the SHA-pinned versions file path for a specific org."""
    return SCRIPT_DIR / f"{org.lower()}-versions-sha.txt"


def get_org_unversioned_file(org: str) -> Path:
    """Get the unversioned cache file path for a specific org."""
    return SCRIPT_DIR / f"{org.lower()}-unversioned.txt"


def get_readme_file() -> Path:
    return SCRIPT_DIR / "README.md"


def get_index_file() -> Path:
    return SCRIPT_DIR / "index.json"


def get_ledger_file() -> Path:
    return SCRIPT_DIR / "seen-versions.json"


def parse_repo(repo_ref: str) -> tuple[str, str]:
    """Parse 'org/repo' format into (org, repo_name) tuple."""
    parts = repo_ref.split("/")
    if len(parts) != 2:
        raise ValueError(f"Invalid repo format: {repo_ref}, expected 'org/repo'")
    return (parts[0], parts[1])


def load_unversioned() -> set[str]:
    """Load the set of repos known to have no vINTEGER tags."""
    unversioned_file = get_unversioned_file()
    if not unversioned_file.exists():
        return set()
    return set(
        line.strip()
        for line in unversioned_file.read_text().splitlines()
        if line.strip()
    )


def save_unversioned(repos: set[str]) -> None:
    """Save the set of repos known to have no vINTEGER tags."""
    with open(get_unversioned_file(), "w") as f:
        for repo_name in sorted(repos):
            f.write(f"{repo_name}\n")


def get_org_readme_markers(org: str) -> tuple[str, str]:
    """Get the README start/end markers for a specific org's versions."""
    return (
        f"<!-- {org.upper()}_VERSIONS_START -->",
        f"<!-- {org.upper()}_VERSIONS_END -->",
    )


def get_org_readme_sha_markers(org: str) -> tuple[str, str]:
    """Get the README start/end markers for a specific org's SHA-pinned versions."""
    return (
        f"<!-- {org.upper()}_VERSIONS_SHA_START -->",
        f"<!-- {org.upper()}_VERSIONS_SHA_END -->",
    )


def load_org_unversioned(org: str) -> set[str]:
    """Load the set of repos known to have no vINTEGER tags for a specific org."""
    file = get_org_unversioned_file(org)
    if not file.exists():
        return set()
    return set(line.strip() for line in file.read_text().splitlines() if line.strip())


def save_org_unversioned(org: str, repos: set[str]) -> None:
    """Save the set of repos known to have no vINTEGER tags for a specific org."""
    file = get_org_unversioned_file(org)
    with open(file, "w") as f:
        for repo_name in sorted(repos):
            f.write(f"{repo_name}\n")


def update_readme(versions_content: str) -> None:
    """Update the README.md with the latest versions in a fenced code block."""
    readme_file = get_readme_file()
    if not readme_file.exists():
        print(f"Warning: {readme_file} not found, skipping README update")
        return

    readme_text = readme_file.read_text()

    # Build the new section content
    new_section = f"""{README_START_MARKER}
## Latest versions

```
{versions_content}```
{README_END_MARKER}"""

    # Check if markers already exist
    if README_START_MARKER in readme_text and README_END_MARKER in readme_text:
        # Replace existing section
        pattern = re.compile(
            re.escape(README_START_MARKER) + r".*?" + re.escape(README_END_MARKER),
            re.DOTALL,
        )
        new_readme = pattern.sub(new_section, readme_text)
    else:
        # Append to end of file
        new_readme = readme_text.rstrip() + "\n\n" + new_section + "\n"

    readme_file.write_text(new_readme)
    print(f"Updated {readme_file} with latest versions")


def update_readme_sha(versions_sha_content: str) -> None:
    """Update the README.md with the latest SHA-pinned versions in a fenced code block."""
    readme_file = get_readme_file()
    if not readme_file.exists():
        print(f"Warning: {readme_file} not found, skipping README SHA update")
        return

    readme_text = readme_file.read_text()

    # Build the new section content
    new_section = f"""{README_SHA_START_MARKER}
## Latest versions (SHA-pinned)

```
{versions_sha_content}```
{README_SHA_END_MARKER}"""

    # Check if markers already exist
    if README_SHA_START_MARKER in readme_text and README_SHA_END_MARKER in readme_text:
        # Replace existing section
        pattern = re.compile(
            re.escape(README_SHA_START_MARKER)
            + r".*?"
            + re.escape(README_SHA_END_MARKER),
            re.DOTALL,
        )
        new_readme = pattern.sub(new_section, readme_text)
    else:
        # Append to end of file
        new_readme = readme_text.rstrip() + "\n\n" + new_section + "\n"

    readme_file.write_text(new_readme)
    print(f"Updated {readme_file} with SHA-pinned versions")


def update_readme_for_org(org: str, versions_content: str) -> None:
    """Update the README.md with a specific org's versions in a collapsible section."""
    readme_file = get_readme_file()
    if not readme_file.exists():
        print(f"Warning: {readme_file} not found, skipping README update for {org}")
        return

    readme_text = readme_file.read_text()
    start_marker, end_marker = get_org_readme_markers(org)

    # Build the new section content
    new_section = f"""{start_marker}
<details>
<summary><h3><code>{org}</code></h3></summary>

```
{versions_content}```

</details>
{end_marker}"""

    # Check if markers already exist
    if start_marker in readme_text and end_marker in readme_text:
        # Replace existing section
        pattern = re.compile(
            re.escape(start_marker) + r".*?" + re.escape(end_marker), re.DOTALL
        )
        new_readme = pattern.sub(new_section, readme_text)
    else:
        # Append to end of file
        new_readme = readme_text.rstrip() + "\n\n" + new_section + "\n"

    readme_file.write_text(new_readme)
    print(f"Updated README with {org} versions")


def update_readme_sha_for_org(org: str, versions_sha_content: str) -> None:
    """Update the README.md with a specific org's SHA-pinned versions in a collapsible section."""
    readme_file = get_readme_file()
    if not readme_file.exists():
        print(f"Warning: {readme_file} not found, skipping README SHA update for {org}")
        return

    readme_text = readme_file.read_text()
    start_marker, end_marker = get_org_readme_sha_markers(org)

    # Build the new section content
    new_section = f"""{start_marker}
<details>
<summary><h3><code>{org}</code> (SHA-pinned)</h3></summary>

```
{versions_sha_content}```

</details>
{end_marker}"""

    # Check if markers already exist
    if start_marker in readme_text and end_marker in readme_text:
        # Replace existing section
        pattern = re.compile(
            re.escape(start_marker) + r".*?" + re.escape(end_marker), re.DOTALL
        )
        new_readme = pattern.sub(new_section, readme_text)
    else:
        # Append to end of file
        new_readme = readme_text.rstrip() + "\n\n" + new_section + "\n"

    readme_file.write_text(new_readme)
    print(f"Updated README with {org} SHA-pinned versions")


def fetch_repos(org: str) -> list[dict]:
    """Fetch all repos for an organization using curl."""
    repos = []
    page = 1
    per_page = 100

    while True:
        url = f"{GITHUB_API_URL}/orgs/{org}/repos?per_page={per_page}&page={page}"
        headers = ["-H", "Accept: application/vnd.github+json"]

        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers.extend(["-H", f"Authorization: token {token}"])

        result = subprocess.run(
            ["curl", "-s"] + headers + [url],
            capture_output=True,
            text=True,
            check=True,
        )

        page_repos = json.loads(result.stdout)

        # Handle error responses (e.g., rate limiting)
        if isinstance(page_repos, dict) and "message" in page_repos:
            print(
                f"API error: {page_repos.get('message', 'Unknown error')}",
                file=sys.stderr,
            )
            break

        if not page_repos:
            break

        repos.extend(page_repos)

        if len(page_repos) < per_page:
            break

        page += 1

    return repos


def fetch_repos_by_search(query: str) -> list[dict]:
    """Fetch repos matching a GitHub search query (e.g. an org plus a topic).

    Returns a list of repo dicts (each with at least "name" and "full_name").
    Used for bundle orgs that also contain many non-action repos, so we can
    select by topic instead of listing the whole org.
    """
    repos: list[dict] = []
    page = 1
    per_page = 100

    while True:
        headers = ["-H", "Accept: application/vnd.github+json"]
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers.extend(["-H", f"Authorization: token {token}"])

        result = subprocess.run(
            ["curl", "-s", "-G"]
            + headers
            + [
                f"{GITHUB_API_URL}/search/repositories",
                "--data-urlencode",
                f"q={query}",
                "--data-urlencode",
                f"per_page={per_page}",
                "--data-urlencode",
                f"page={page}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        data = json.loads(result.stdout)

        # Handle error responses (e.g., rate limiting, invalid query)
        if not isinstance(data, dict) or "items" not in data:
            message = data.get("message") if isinstance(data, dict) else None
            if message:
                print(f"Search API error: {message}", file=sys.stderr)
            break

        items = data["items"]
        if not items:
            break

        repos.extend(items)

        if len(items) < per_page:
            break

        page += 1

    return repos


def is_action_repo(org: str, repo_name: str) -> bool:
    """Return True if the repo has a root action.yml/action.yaml.

    That is what makes a repo usable as `uses: org/repo@tag`, so it filters out
    libraries, reusable workflows, and tools that merely carry version tags or
    the github-actions topic.
    """
    for filename in ("action.yml", "action.yaml"):
        headers = ["-H", "Accept: application/vnd.github+json"]
        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers.extend(["-H", f"Authorization: token {token}"])

        result = subprocess.run(
            ["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}"]
            + headers
            + [f"{GITHUB_API_URL}/repos/{org}/{repo_name}/contents/{filename}"],
            capture_output=True,
            text=True,
            check=True,
        )
        status = result.stdout.strip()
        if status == "200":
            return True
        if status != "404":
            print(
                f"Warning: unexpected HTTP {status} checking "
                f"{org}/{repo_name}/{filename}; treating as not an action",
                file=sys.stderr,
            )
    return False


def fetch_tags(org: str, repo_name: str) -> list[tuple[str, str]]:
    """Fetch all tags for a repository using the GitHub API.

    Returns a list of (tag_name, commit_sha) tuples.
    """
    tags = []
    page = 1
    per_page = 100

    while True:
        url = f"{GITHUB_API_URL}/repos/{org}/{repo_name}/tags?per_page={per_page}&page={page}"
        headers = ["-H", "Accept: application/vnd.github+json"]

        token = os.environ.get("GITHUB_TOKEN")
        if token:
            headers.extend(["-H", f"Authorization: token {token}"])

        result = subprocess.run(
            ["curl", "-s"] + headers + [url],
            capture_output=True,
            text=True,
            check=True,
        )

        page_tags = json.loads(result.stdout)

        # Handle error responses (e.g., rate limiting)
        if isinstance(page_tags, dict) and "message" in page_tags:
            print(
                f"  API error for {repo_name}: {page_tags['message']}", file=sys.stderr
            )
            break

        if not page_tags:
            break

        tags.extend((tag["name"], tag["commit"]["sha"]) for tag in page_tags)

        if len(page_tags) < per_page:
            break

        page += 1

    return tags


SEMVER_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")


def parse_semver_tags(
    tags: list[tuple[str, str]],
) -> list[tuple[tuple[int, int, int], str, str]]:
    """Return exact vX.Y.Z tags as (version, tag_name, sha), newest first.

    Bare major (v5) and two-part (v4.1) tags are excluded: they are mutable
    pointers and cannot carry the quarantine guarantee.
    """
    out: list[tuple[tuple[int, int, int], str, str]] = []
    for name, sha in tags:
        name = name.strip()
        match = SEMVER_RE.match(name)
        if match:
            version = (int(match[1]), int(match[2]), int(match[3]))
            out.append((version, name, sha))
    out.sort(reverse=True, key=lambda x: x[0])
    return out


ANY_VERSION_RE = re.compile(r"^v\d+(\.\d+){0,2}$")


def has_version_tag(tags: list[tuple[str, str]]) -> bool:
    """True if any tag looks like a version (v1, v1.2, v1.2.3)."""
    return any(ANY_VERSION_RE.match(name.strip()) for name, _ in tags)


def record_observation(
    ledger: dict, repo_ref: str, tag: str, sha: str, today: date
) -> bool:
    """Record one (repo, tag, sha) observation. Mutates `ledger` in place.

    Returns True only on the run that newly poisons an entry (an immutable tag
    whose SHA moved), so the caller can open a single tag-moved issue.
    """
    repo = ledger.setdefault(repo_ref, {})
    entry = repo.get(tag)
    if entry is None:
        repo[tag] = {"sha": sha, "first_seen": today.isoformat()}
        return False
    if entry.get("bad"):
        return False
    if entry["sha"] != sha:
        entry["bad"] = True
        return True
    return False


def select_quarantined_version(
    ledger: dict,
    repo_ref: str,
    upstream_semver: list[tuple[tuple[int, int, int], str, str]],
    today: date,
) -> tuple[str, str] | None:
    """Return the (tag, sha) to offer, or None if nothing qualifies.

    A tag qualifies when its ledger entry is not `bad`, its `first_seen` is at
    least QUARANTINE_DAYS old, and the ledger SHA still matches upstream.
    `upstream_semver` is the output of `parse_semver_tags` (newest first).
    """
    cutoff = today - timedelta(days=QUARANTINE_DAYS)
    repo = ledger.get(repo_ref, {})
    candidates: list[tuple[tuple[int, int, int], str, str]] = []
    for version, tag, upstream_sha in upstream_semver:
        entry = repo.get(tag)
        if entry is None or entry.get("bad"):
            continue
        if date.fromisoformat(entry["first_seen"]) > cutoff:
            continue
        if entry["sha"] != upstream_sha:
            continue
        candidates.append((version, tag, upstream_sha))
    if not candidates:
        return None
    candidates.sort(reverse=True, key=lambda x: x[0])
    _, tag, sha = candidates[0]
    return (tag, sha)


GRANDFATHER_LINE_RE = re.compile(r"^(\S+)@([0-9a-fA-F]+)\s*#\s*(\S+)\s*$")


def grandfather_ledger() -> dict:
    """Seed a ledger from the committed *-versions-sha.txt files.

    Treats every already-published version as trusted (first_seen far in the
    past) so the first run after introducing the ledger has no 14-day blackout.
    """
    ledger: dict = {}
    sha_files = [get_versions_sha_file()] + [
        get_org_versions_sha_file(org) for org in ADDITIONAL_ORGS
    ]
    for path in sha_files:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            match = GRANDFATHER_LINE_RE.match(line.strip())
            if not match:
                continue
            repo_ref, sha, tag = match[1], match[2], match[3]
            ledger.setdefault(repo_ref, {})[tag] = {
                "sha": sha,
                "first_seen": GRANDFATHER_DATE.isoformat(),
            }
    return ledger


def load_ledger() -> dict:
    """Load seen-versions.json, or grandfather-seed it when absent."""
    path = get_ledger_file()
    if path.exists():
        try:
            return json.loads(path.read_text())
        except json.JSONDecodeError as e:
            print(
                f"Error: {path} is not valid JSON ({e}). "
                "Fix or remove the file and re-run.",
                file=sys.stderr,
            )
            sys.exit(1)
    return grandfather_ledger()


def save_ledger(ledger: dict) -> None:
    """Write seen-versions.json with repos and tags sorted for stable diffs."""
    ordered = {
        repo: dict(sorted(tags.items()))
        for repo, tags in sorted(ledger.items(), key=lambda item: item[0].lower())
    }
    get_ledger_file().write_text(json.dumps(ordered, indent=2) + "\n")


def get_base_url() -> str:
    """Attempt to derive base URL from git repository, with fallback."""
    try:
        result = subprocess.run(
            ["git", "config", "--get", "remote.origin.url"],
            capture_output=True,
            text=True,
            check=False,
        )

        if result.returncode == 0 and result.stdout:
            git_url = result.stdout.strip()

            # Parse GitHub HTTPS URL
            # https://github.com/user/repo.git -> https://user.github.io/repo/
            if git_url.startswith("https://github.com/"):
                # Extract user/repo
                parts = git_url.replace(".git", "").split("/")
                if len(parts) >= 2:
                    user, repo = parts[-2], parts[-1]
                    return f"https://{user}.github.io/{repo}/"

            # Parse GitHub SSH URL
            # git@github.com:user/repo.git -> https://user.github.io/repo/
            elif git_url.startswith("git@github.com:"):
                # Extract user/repo (SSH format uses colon instead of slash)
                parts = git_url.replace(".git", "").split(":")[-1].split("/")
                if len(parts) >= 2:
                    user, repo = parts[0], parts[1]
                    return f"https://{user}.github.io/{repo}/"

        # Fallback to hardcoded URL
        return BASE_URL
    except (subprocess.SubprocessError, FileNotFoundError):
        return BASE_URL


def generate_index_json() -> None:
    """Generate index.json file listing all available bundles."""
    base_url = get_base_url()

    # Build index structure
    index = {"bundles": {}, "orgs": {}}

    # Add default bundle (generic + ADDITIONAL_REPOS)
    index["bundles"]["default"] = {
        "versions_url": f"{base_url}versions.txt",
        "versions_sha_url": f"{base_url}versions-sha.txt",
    }

    # Add each additional org, sorted alphabetically
    for org in sorted(ADDITIONAL_ORGS, key=str.lower):
        org_key = org.lower()
        index["orgs"][org_key] = {
            "versions_url": f"{base_url}{org_key}-versions.txt",
            "versions_sha_url": f"{base_url}{org_key}-versions-sha.txt",
        }

    # Write index.json
    with open(get_index_file(), "w") as f:
        json.dump(index, f, indent=2)

    print(f"Generated {get_index_file()}")


def load_versioned_repos(*files: Path) -> set[str]:
    """Load repo refs from versions files (lines of 'org/repo@tag')."""
    repos: set[str] = set()
    for path in files:
        if path.exists():
            for line in path.read_text().splitlines():
                line = line.strip()
                if line and "@" in line:
                    repos.add(line.split("@")[0])
    return repos


def detect_regressions(
    old_unversioned: set[str],
    new_unversioned: set[str],
    old_org_unversioned: dict[str, set[str]],
    new_org_unversioned: dict[str, set[str]],
    old_versioned: set[str] | None = None,
) -> list[str]:
    """Return sorted list of repo refs that regressed from versioned to unversioned.

    If old_versioned is provided, only repos that were previously versioned
    (present in old versions files) are flagged as regressions. This prevents
    false positives from cache loading inconsistencies.
    """
    regressions: set[str] = set()

    # Main org regressions
    regressions.update(new_unversioned - old_unversioned)

    # Per-org regressions
    all_orgs = set(old_org_unversioned.keys()) | set(new_org_unversioned.keys())
    for org in all_orgs:
        old_set = old_org_unversioned.get(org, set())
        new_set = new_org_unversioned.get(org, set())
        regressions.update(new_set - old_set)

    # Filter to only repos that were previously versioned
    if old_versioned is not None:
        regressions &= old_versioned

    return sorted(regressions)


def report_regression(repo_ref: str) -> None:
    """Report a regression to stderr when not running in CI."""
    print(
        f"REGRESSION: {repo_ref} was previously versioned but no version tags found",
        file=sys.stderr,
    )
    print(
        f"  This may be a transient issue (API error, rate limit, etc.).",
        file=sys.stderr,
    )
    print(
        f"  Check: {GITHUB_API_URL}/repos/{repo_ref}/tags",
        file=sys.stderr,
    )


def create_regression_issue(repo_ref: str) -> None:
    """Create a GitHub issue alerting that a repo regressed to unversioned.

    Only runs when GITHUB_ACTIONS env var is set (i.e., in CI).
    Reports to stderr when not in CI.
    Skips if an open regression issue already exists for this repo.
    """
    if os.environ.get("GITHUB_ACTIONS") != "true":
        report_regression(repo_ref)
        return

    try:
        # Check for existing open regression issue
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--label",
                "regression",
                "--state",
                "open",
                "--search",
                f"Regression: {repo_ref}",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            print(f"Skipping {repo_ref}: existing open regression issue found")
            return

        # Ensure label exists
        subprocess.run(
            [
                "gh",
                "label",
                "create",
                "regression",
                "--color",
                "B60205",
                "--description",
                "Repo regressed from versioned to unversioned",
                "--force",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        # Build workflow run link
        run_link = ""
        if (
            os.environ.get("GITHUB_SERVER_URL")
            and os.environ.get("GITHUB_REPOSITORY")
            and os.environ.get("GITHUB_RUN_ID")
        ):
            run_link = f"{os.environ['GITHUB_SERVER_URL']}/{os.environ['GITHUB_REPOSITORY']}/actions/runs/{os.environ['GITHUB_RUN_ID']}"

        body = (
            f"The repo `{repo_ref}` was previously versioned but no version tags\n"
            f"were found in the latest run.\n"
            f"\n"
            f"This may be a transient issue (API error, rate limit, etc.).\n"
            f"\n"
            f"**To resolve:**\n"
            f"1. Investigate the repo manually\n"
            f"2. If transient: remove `{repo_ref}` from the unversioned cache file and close this issue\n"
            f"3. If genuinely unversioned: close this issue as not planned\n"
        )
        if run_link:
            body += f"\n**Workflow run:** {run_link}\n"

        subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                f"Regression: {repo_ref} moved to unversioned",
                "--body",
                body,
                "--label",
                "regression",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Created regression issue for {repo_ref}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(
            f"Warning: failed to create regression issue for {repo_ref}: {e}",
            file=sys.stderr,
        )


def build_discovery_worklist() -> list[tuple[str, str, str]]:
    """Build the (repo_ref, org, repo_name) work list via full org discovery.

    Fetches every repo from ORG_NAME and each bundle org (using search or full
    listing), then assembles the combined list. Used by discover runs.
    """
    # Fetch repos from the main organization
    print(f"Fetching repos for {ORG_NAME}...")
    org_repos = fetch_repos(ORG_NAME)
    print(f"Found {len(org_repos)} repos")

    # Fetch repos from additional orgs. "search" orgs are narrowed by a query;
    # the rest are full-org listings. Non-action repos are dropped later by
    # is_action_repo().
    additional_orgs_repos: dict[str, list[dict]] = {}
    for additional_org in ADDITIONAL_ORGS:
        bundle = ORG_BUNDLES.get(additional_org, {"source": "full"})
        if bundle.get("source") == "search":
            org_repos_list = fetch_repos_by_search(bundle["query"])
            print(f"Found {len(org_repos_list)} repos for {additional_org} via search")
        else:
            print(f"Fetching repos for {additional_org}...")
            org_repos_list = fetch_repos(additional_org)
            print(f"Found {len(org_repos_list)} repos for {additional_org}")
        additional_orgs_repos[additional_org] = org_repos_list

    # Build list of repos to process: combine org repos with additional repos
    repos_to_process: list[tuple[str, str, str]] = []

    # Add repos from main organization, excluding skipped ones
    skipped_count = 0
    for repo in org_repos:
        repo_name = repo["name"]
        if repo_name in SKIP_REPOS:
            skipped_count += 1
            continue
        repos_to_process.append((f"{ORG_NAME}/{repo_name}", ORG_NAME, repo_name))

    if skipped_count > 0:
        print(f"Skipped {skipped_count} repos from {ORG_NAME}")

    # Add additional repos
    for additional_repo in ADDITIONAL_REPOS:
        org, repo_name = parse_repo(additional_repo)
        repos_to_process.append((additional_repo, org, repo_name))

    # Add repos from additional orgs
    for additional_org, org_repos_list in additional_orgs_repos.items():
        for repo in org_repos_list:
            repo_name = repo["name"]
            repo_ref = f"{additional_org}/{repo_name}"
            repos_to_process.append((repo_ref, additional_org, repo_name))

    return repos_to_process


def load_tracked_repos() -> list[tuple[str, str, str]]:
    """Build the (repo_ref, org, repo_name) work list from the existing version
    files. Used by refresh runs to re-check known repos without re-discovering."""
    work: list[tuple[str, str, str]] = []
    seen: set[str] = set()
    files = [get_versions_file()] + [
        get_org_versions_file(org) for org in ADDITIONAL_ORGS
    ]
    for path in files:
        if not path.exists():
            continue
        for line in path.read_text().splitlines():
            line = line.strip()
            if not line or "@" not in line:
                continue
            repo_ref = line.split("@", 1)[0]
            if repo_ref in seen:
                continue
            seen.add(repo_ref)
            org, repo_name = parse_repo(repo_ref)
            work.append((repo_ref, org, repo_name))
    return work


def create_tag_moved_issue(repo_ref: str, tag: str) -> None:
    """Alert that an immutable tag's SHA moved (a supply-chain tamper signal).

    Only runs in CI (GITHUB_ACTIONS=true); otherwise reports to stderr.
    Skips if an open tag-moved issue already exists for this repo+tag.
    """
    title = f"Tag moved: {repo_ref}@{tag}"
    if os.environ.get("GITHUB_ACTIONS") != "true":
        print(f"Tamper signal: {title} (SHA changed on an immutable tag)",
              file=sys.stderr)
        return

    try:
        result = subprocess.run(
            [
                "gh",
                "issue",
                "list",
                "--label",
                "tag-moved",
                "--state",
                "open",
                "--search",
                title,
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        if result.stdout.strip():
            print(f"Skipping {repo_ref}@{tag}: existing open tag-moved issue found")
            return

        # Ensure label exists
        subprocess.run(
            [
                "gh",
                "label",
                "create",
                "tag-moved",
                "--color",
                "B60205",
                "--description",
                "Immutable tag SHA changed (possible tampering)",
                "--force",
            ],
            capture_output=True,
            text=True,
            check=True,
        )

        # Build workflow run link
        run_link = ""
        if (
            os.environ.get("GITHUB_SERVER_URL")
            and os.environ.get("GITHUB_REPOSITORY")
            and os.environ.get("GITHUB_RUN_ID")
        ):
            run_link = (
                f"{os.environ['GITHUB_SERVER_URL']}/"
                f"{os.environ['GITHUB_REPOSITORY']}/actions/runs/"
                f"{os.environ['GITHUB_RUN_ID']}"
            )

        body = (
            f"The immutable tag `{tag}` of `{repo_ref}` now points at a\n"
            f"different commit than first recorded in `seen-versions.json`.\n"
            f"\n"
            f"This is a supply-chain tamper signal. The version has been marked\n"
            f"`bad` in the ledger and will never be offered again.\n"
            f"\n"
            f"**To resolve:**\n"
            f"1. Investigate why the tag moved.\n"
            f"2. If legitimate, remove the `bad` entry from `seen-versions.json`\n"
            f"   so the tag re-enters quarantine, then close this issue.\n"
        )
        if run_link:
            body += f"\n**Workflow run:** {run_link}\n"

        subprocess.run(
            [
                "gh",
                "issue",
                "create",
                "--title",
                title,
                "--body",
                body,
                "--label",
                "tag-moved",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        print(f"Created tag-moved issue for {repo_ref}@{tag}")
    except (subprocess.CalledProcessError, FileNotFoundError) as e:
        print(
            f"Warning: failed to create tag-moved issue for {repo_ref}@{tag}: {e}",
            file=sys.stderr,
        )


def main(discover: bool = True):
    """Main function to fetch repos, get tags via API, and generate versions.txt."""
    # Load cached unversioned repos
    unversioned = load_unversioned()
    if unversioned:
        print(f"Loaded {len(unversioned)} known unversioned repos from cache")

    # Load per-org unversioned caches
    org_unversioned: dict[str, set[str]] = {}
    for org in ADDITIONAL_ORGS:
        org_unversioned[org] = load_org_unversioned(org)
        if org_unversioned[org]:
            print(
                f"Loaded {len(org_unversioned[org])} known unversioned repos for {org}"
            )

    # Capture the previously-versioned repos before this run overwrites the
    # version files, so regression detection compares against the prior run
    # rather than its own fresh output.
    old_versioned = load_versioned_repos(
        get_versions_file(),
        *(get_org_versions_file(org) for org in ADDITIONAL_ORGS),
    )

    if discover:
        repos_to_process = build_discovery_worklist()
    else:
        print("Refresh mode: re-checking already-tracked repos")
        repos_to_process = load_tracked_repos()
        if not repos_to_process:
            print(
                "Refresh found no tracked repos (version files missing or empty); "
                "skipping to avoid clobbering them. Run a discovery pass first.",
                file=sys.stderr,
            )
            return
    print(f"Processing {len(repos_to_process)} repos")

    versions = []
    versions_sha = []
    new_unversioned = set()
    new_org_unversioned: dict[str, set[str]] = {}

    # Track org-specific versions separately
    org_versions: dict[str, list[tuple[str, str]]] = {}
    org_versions_sha: dict[str, list[tuple[str, str, str]]] = {}

    # Quarantine ledger and tamper signals.
    ledger = load_ledger()
    today = datetime.now(timezone.utc).date()
    poisoned: list[tuple[str, str]] = []

    for repo_ref, org, repo_name in repos_to_process:
        # Determine which unversioned cache to use
        if org in ADDITIONAL_ORGS:
            org_cache = org_unversioned.get(org, set())
        else:
            org_cache = unversioned

        # Skip repos known to have no vINTEGER tags
        if repo_ref in org_cache:
            print(f"Skipping {repo_ref} (cached as unversioned)")
            if org in ADDITIONAL_ORGS:
                if org not in new_org_unversioned:
                    new_org_unversioned[org] = set()
                new_org_unversioned[org].add(repo_ref)
            else:
                new_unversioned.add(repo_ref)
            continue

        print(f"Fetching tags for {repo_ref}...", end=" ")
        tags = fetch_tags(org, repo_name)
        semver_tags = parse_semver_tags(tags)

        # Bundle orgs may contain non-action repos; keep only real actions
        # (discovery only — refresh trusts the already-tracked set).
        if discover and org in ADDITIONAL_ORGS and semver_tags:
            if not is_action_repo(org, repo_name):
                print("not an action")
                continue

        # Record observations and collect newly-poisoned tags.
        for _, tag, sha in semver_tags:
            if record_observation(ledger, repo_ref, tag, sha, today):
                poisoned.append((repo_ref, tag))

        selected = select_quarantined_version(ledger, repo_ref, semver_tags, today)

        if selected:
            tag, commit_sha = selected
            print(f"{tag} (cleared quarantine)")
            if org in ADDITIONAL_ORGS:
                org_versions.setdefault(org, []).append((repo_ref, tag))
                org_versions_sha.setdefault(org, []).append(
                    (repo_ref, commit_sha, tag))
            else:
                versions.append((repo_ref, tag))
                versions_sha.append((repo_ref, commit_sha, tag))
        elif not has_version_tag(tags):
            # No version-shaped tags at all (e.g. only 'latest', 'main').
            # Cache as unversioned so future runs skip the API call.
            print("no version tag")
            if org in ADDITIONAL_ORGS:
                new_org_unversioned.setdefault(org, set()).add(repo_ref)
            else:
                new_unversioned.add(repo_ref)
        else:
            # Has versions but none cleared quarantine yet; re-check next run.
            print("no quarantined version yet")

    # Sort alphabetically by repo reference
    versions.sort(key=lambda x: x[0].lower())
    versions_sha.sort(key=lambda x: x[0].lower())

    # Build versions content
    versions_content = (
        "\n".join(f"{repo_ref}@{tag}" for repo_ref, tag in versions) + "\n"
    )

    # Write versions.txt
    with open(get_versions_file(), "w") as f:
        f.write(versions_content)

    # Build versions-sha.txt content
    versions_sha_content = (
        "\n".join(
            f"{repo_ref}@{commit_sha} # {tag}"
            for repo_ref, commit_sha, tag in versions_sha
        )
        + "\n"
    )

    # Write versions-sha.txt
    with open(get_versions_sha_file(), "w") as f:
        f.write(versions_sha_content)

    # Update README.md with the versions
    update_readme(versions_content)

    # Update README.md with the SHA-pinned versions
    update_readme_sha(versions_sha_content)

    print(f"\nWrote {len(versions)} versions to {get_versions_file()}")
    print(f"Wrote {len(versions_sha)} versions with SHAs to {get_versions_sha_file()}")

    # Update unversioned.txt (discovery only; refresh must not clobber the cache)
    if discover:
        save_unversioned(new_unversioned)
        print(
            f"Cached {len(new_unversioned)} unversioned repos to {get_unversioned_file()}"
        )

    # Write per-org files and update README sections
    for additional_org in ADDITIONAL_ORGS:
        # Get versions for this org from org-specific lists
        org_versions_list = org_versions.get(additional_org, [])
        org_versions_sha_list = org_versions_sha.get(additional_org, [])

        if org_versions_list:
            # Sort alphabetically
            org_versions_list.sort(key=lambda x: x[0].lower())
            org_versions_sha_list.sort(key=lambda x: x[0].lower())

            # Build content
            org_versions_content = (
                "\n".join(f"{repo_ref}@{tag}" for repo_ref, tag in org_versions_list)
                + "\n"
            )
            org_versions_sha_content = (
                "\n".join(
                    f"{repo_ref}@{commit_sha} # {tag}"
                    for repo_ref, commit_sha, tag in org_versions_sha_list
                )
                + "\n"
            )

            # Write files
            org_versions_file = get_org_versions_file(additional_org)
            with open(org_versions_file, "w") as f:
                f.write(org_versions_content)
            print(f"Wrote {len(org_versions_list)} versions to {org_versions_file}")

            org_versions_sha_file = get_org_versions_sha_file(additional_org)
            with open(org_versions_sha_file, "w") as f:
                f.write(org_versions_sha_content)
            print(
                f"Wrote {len(org_versions_sha_list)} SHA versions to {org_versions_sha_file}"
            )

            # Update README
            update_readme_for_org(additional_org, org_versions_content)
            update_readme_sha_for_org(additional_org, org_versions_sha_content)

        # Update per-org unversioned cache (discovery only)
        if discover and additional_org in new_org_unversioned:
            save_org_unversioned(additional_org, new_org_unversioned[additional_org])
            print(
                f"Cached {len(new_org_unversioned[additional_org])} unversioned repos for {additional_org}"
            )

    # Generate index.json
    generate_index_json()

    # Persist the ledger and alert on any tags poisoned this run.
    save_ledger(ledger)
    print(f"Ledger saved to {get_ledger_file()}")
    for repo_ref, tag in poisoned:
        create_tag_moved_issue(repo_ref, tag)

    # Detect and report regressions
    if discover:
        regressions = detect_regressions(
            unversioned,
            new_unversioned,
            org_unversioned,
            new_org_unversioned,
            old_versioned,
        )
        if regressions:
            print(f"\nDetected {len(regressions)} regressions:")
            for repo_ref in regressions:
                print(f"  - {repo_ref}")
                create_regression_issue(repo_ref)


if __name__ == "__main__":
    main(discover="--refresh" not in sys.argv)
