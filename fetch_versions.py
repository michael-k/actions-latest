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
from pathlib import Path


# Base URL with fallback
BASE_URL = "https://michael-k.github.io/actions-latest/"

# Markers for the README section
README_START_MARKER = "<!-- VERSIONS_START -->"
README_END_MARKER = "<!-- VERSIONS_END -->"
README_SHA_START_MARKER = "<!-- VERSIONS_SHA_START -->"
README_SHA_END_MARKER = "<!-- VERSIONS_SHA_END -->"
ORG_NAME = "actions"
ADDITIONAL_REPOS: list[str] = [
    "astral-sh/setup-uv",
    "dependabot/fetch-metadata",
    "dorny/paths-filter",
    "golangci/golangci-lint-action",
    "goreleaser/goreleaser-action",
    "jdx/mise-action",
    "ruby/setup-ruby",
    "taiki-e/install-action",
]
ADDITIONAL_ORGS: list[str] = [
    "aws-actions",
    "docker",
]
# Bundle orgs sourced from a GitHub topic search instead of a full-org listing,
# for orgs that also contain many non-action repos (e.g. docker).
SEARCH_ORGS: dict[str, str] = {
    "docker": "org:docker topic:github-actions",
}
# Repos that match a SEARCH_ORGS query but are not usable actions.
SEARCH_ORG_EXCLUDE: set[str] = {
    "docker/github-builder",   # reusable workflow, not an action
    "docker/actions-toolkit",  # TypeScript library, not an action
}
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


SCRIPT_DIR = Path(__file__).parent.resolve()


def get_versions_file() -> Path:
    return SCRIPT_DIR / "versions.txt"


def get_versions_sha_file() -> Path:
    return SCRIPT_DIR / "versions-sha.txt"


def get_unversioned_file() -> Path:
    return SCRIPT_DIR / "unversioned.txt"


def get_org_versions_file(org: str) -> Path:
    """Get the versions file path for a specific org."""
    return SCRIPT_DIR / f"{org}-versions.txt"


def get_org_versions_sha_file(org: str) -> Path:
    """Get the SHA-pinned versions file path for a specific org."""
    return SCRIPT_DIR / f"{org}-versions-sha.txt"


def get_org_unversioned_file(org: str) -> Path:
    """Get the unversioned cache file path for a specific org."""
    return SCRIPT_DIR / f"{org}-unversioned.txt"


def get_readme_file() -> Path:
    return SCRIPT_DIR / "README.md"


def get_index_file() -> Path:
    return SCRIPT_DIR / "index.json"


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


def get_latest_version_tag(tags: list[tuple[str, str]]) -> str | None:
    """Get the latest vINTEGER tag from a list of (tag_name, commit_sha) tuples.

    Returns only the tag name.
    """
    # Filter to vINTEGER tags (e.g., v1, v2, v10)
    version_pattern = re.compile(r"^v(\d+)$")
    version_tags = []

    for tag_name, _ in tags:
        match = version_pattern.match(tag_name.strip())
        if match:
            version_tags.append((int(match.group(1)), tag_name.strip()))

    if not version_tags:
        return None

    # Sort by version number descending and return the latest tag name
    version_tags.sort(reverse=True, key=lambda x: x[0])
    return version_tags[0][1]


def get_latest_semver_tag(tags: list[tuple[str, str]]) -> tuple[str, str] | None:
    """Get the latest semantic version tag from a list of (tag_name, commit_sha) tuples.

    Returns a tuple of (tag_name, commit_sha) or None if no semver tag found.

    Supports semver format: vX.Y.Z where X, Y, Z are integers.
    """
    # Filter to semver tags (e.g., v1.2.3, v2.0.0)
    version_pattern = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
    version_major_pattern = re.compile(r"^v(\d+)$")
    version_tags = []

    for tag_name, commit_sha in tags:
        tname = tag_name.strip()
        if match := version_pattern.match(tname):
            major = int(match.group(1))
            minor = int(match.group(2))
            patch = int(match.group(3))
            version_tags.append(((major, minor, patch), tname, commit_sha))
        elif match := version_major_pattern.match(tname):
            major = int(match.group(1))
            version_tags.append(((major, 0, 0), tname, commit_sha))

    if not version_tags:
        return None

    # Sort by version number descending (major, minor, patch)
    version_tags.sort(reverse=True, key=lambda x: x[0])
    return (version_tags[0][1], version_tags[0][2])


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

    # Add each additional org
    for org in ADDITIONAL_ORGS:
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


def main():
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

    # Fetch repos from the main organization
    print(f"Fetching repos for {ORG_NAME}...")
    org_repos = fetch_repos(ORG_NAME)
    print(f"Found {len(org_repos)} repos")

    # Fetch repos from additional orgs (search-sourced ones are filtered by an
    # exclude list; the rest are full-org listings).
    additional_orgs_repos: dict[str, list[dict]] = {}
    for additional_org in ADDITIONAL_ORGS:
        if additional_org in SEARCH_ORGS:
            found = fetch_repos_by_search(SEARCH_ORGS[additional_org])
            org_repos_list = [
                repo for repo in found
                if repo.get("full_name") not in SEARCH_ORG_EXCLUDE
            ]
            print(
                f"Found {len(org_repos_list)} repos for {additional_org} via search"
                f" ({len(found) - len(org_repos_list)} excluded)"
            )
        else:
            print(f"Fetching repos for {additional_org}...")
            org_repos_list = fetch_repos(additional_org)
            print(f"Found {len(org_repos_list)} repos for {additional_org}")
        additional_orgs_repos[additional_org] = org_repos_list

    # Build list of repos to process: combine org repos with additional repos
    repos_to_process = []

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
    for additional_org, org_repos in additional_orgs_repos.items():
        for repo in org_repos:
            repo_name = repo["name"]
            repo_ref = f"{additional_org}/{repo_name}"
            repos_to_process.append((repo_ref, additional_org, repo_name))

    additional_orgs_repo_count = sum(
        len(org_repos) for org_repos in additional_orgs_repos.values()
    )
    print(
        f"Processing {len(repos_to_process)} repos total (including {len(ADDITIONAL_REPOS)} additional repos and {additional_orgs_repo_count} from additional orgs)"
    )

    versions = []
    versions_sha = []
    new_unversioned = set()
    new_org_unversioned: dict[str, set[str]] = {}

    # Track org-specific versions separately
    org_versions: dict[str, list[tuple[str, str]]] = {}
    org_versions_sha: dict[str, list[tuple[str, str, str]]] = {}

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
        latest_tag = get_latest_version_tag(tags)
        latest_semver = get_latest_semver_tag(tags)

        if latest_tag:
            # Use vINTEGER tag (preferred)
            print(f"{latest_tag}")

            # Add to appropriate collection based on org
            if org in ADDITIONAL_ORGS:
                if org not in org_versions:
                    org_versions[org] = []
                if org not in org_versions_sha:
                    org_versions_sha[org] = []
                org_versions[org].append((repo_ref, latest_tag))
                if latest_semver:
                    semver_tag, commit_sha = latest_semver
                    org_versions_sha[org].append((repo_ref, commit_sha, semver_tag))
            else:
                versions.append((repo_ref, latest_tag))
                if latest_semver:
                    semver_tag, commit_sha = latest_semver
                    versions_sha.append((repo_ref, commit_sha, semver_tag))
        elif latest_semver:
            # Fallback to semver tag when no vINTEGER tag exists
            semver_tag, commit_sha = latest_semver
            print(f"{semver_tag} (semver fallback)")

            # Add to appropriate collection based on org
            if org in ADDITIONAL_ORGS:
                if org not in org_versions:
                    org_versions[org] = []
                if org not in org_versions_sha:
                    org_versions_sha[org] = []
                org_versions[org].append((repo_ref, semver_tag))
                org_versions_sha[org].append((repo_ref, commit_sha, semver_tag))
            else:
                versions.append((repo_ref, semver_tag))
                versions_sha.append((repo_ref, commit_sha, semver_tag))
        else:
            # No version tags at all
            print("no version tag")
            if org in ADDITIONAL_ORGS:
                if org not in new_org_unversioned:
                    new_org_unversioned[org] = set()
                new_org_unversioned[org].add(repo_ref)
            else:
                new_unversioned.add(repo_ref)

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

    # Update unversioned.txt
    save_unversioned(new_unversioned)

    print(f"\nWrote {len(versions)} versions to {get_versions_file()}")
    print(f"Wrote {len(versions_sha)} versions with SHAs to {get_versions_sha_file()}")
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

        # Update per-org unversioned cache
        if additional_org in new_org_unversioned:
            save_org_unversioned(additional_org, new_org_unversioned[additional_org])
            print(
                f"Cached {len(new_org_unversioned[additional_org])} unversioned repos for {additional_org}"
            )

    # Generate index.json
    generate_index_json()

    # Detect and report regressions
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
    main()
