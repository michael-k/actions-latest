#!/usr/bin/env python3
"""
Unit tests for fetch_versions.py
"""

import json
import os
import subprocess
import tempfile
import unittest
from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import fetch_versions


class TestFetchRepos(unittest.TestCase):
    """Tests for the fetch_repos function."""

    @patch("fetch_versions.subprocess.run")
    def test_fetch_repos_single_page(self, mock_run):
        """Test fetching repos when all fit on one page."""
        mock_repos = [
            {
                "name": "setup-python",
                "clone_url": "https://github.com/actions/setup-python.git",
            },
            {
                "name": "setup-node",
                "clone_url": "https://github.com/actions/setup-node.git",
            },
        ]

        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_repos),
            returncode=0,
        )

        repos = fetch_versions.fetch_repos("actions")

        self.assertEqual(len(repos), 2)
        self.assertEqual(repos[0]["name"], "setup-python")
        self.assertEqual(repos[1]["name"], "setup-node")

    @patch("fetch_versions.subprocess.run")
    def test_fetch_repos_multiple_pages(self, mock_run):
        """Test fetching repos when pagination is needed."""
        # First page - full page of 100 repos
        first_page = [
            {
                "name": f"repo-{i}",
                "clone_url": f"https://github.com/actions/repo-{i}.git",
            }
            for i in range(100)
        ]
        # Second page - partial page (last page)
        second_page = [
            {"name": "repo-100", "clone_url": "https://github.com/actions/repo-100.git"}
        ]

        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(first_page), returncode=0),
            MagicMock(stdout=json.dumps(second_page), returncode=0),
        ]

        repos = fetch_versions.fetch_repos("actions")

        self.assertEqual(len(repos), 101)
        self.assertEqual(repos[0]["name"], "repo-0")
        self.assertEqual(repos[-1]["name"], "repo-100")

    @patch("fetch_versions.subprocess.run")
    def test_fetch_repos_empty(self, mock_run):
        """Test fetching repos when org has no repos."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps([]),
            returncode=0,
        )

        repos = fetch_versions.fetch_repos("actions")

        self.assertEqual(len(repos), 0)


class TestFetchTags(unittest.TestCase):
    """Tests for the fetch_tags function."""

    @patch("fetch_versions.subprocess.run")
    def test_fetch_tags_single_page(self, mock_run):
        """Test fetching tags when all fit on one page."""
        mock_tags = [
            {"name": "v1", "commit": {"sha": "sha1"}},
            {"name": "v2", "commit": {"sha": "sha2"}},
        ]

        mock_run.return_value = MagicMock(
            stdout=json.dumps(mock_tags),
            returncode=0,
        )

        tags = fetch_versions.fetch_tags("actions", "some-repo")

        self.assertEqual(len(tags), 2)
        self.assertEqual(tags[0], ("v1", "sha1"))
        self.assertEqual(tags[1], ("v2", "sha2"))

    @patch("fetch_versions.subprocess.run")
    def test_fetch_tags_multiple_pages(self, mock_run):
        """Test fetching tags when pagination is needed."""
        first_page = [{"name": f"v{i}", "commit": {"sha": f"sha{i}"}} for i in range(100)]
        second_page = [{"name": "v100", "commit": {"sha": "sha100"}}]

        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(first_page), returncode=0),
            MagicMock(stdout=json.dumps(second_page), returncode=0),
        ]

        tags = fetch_versions.fetch_tags("actions", "some-repo")

        self.assertEqual(len(tags), 101)

    @patch("fetch_versions.subprocess.run")
    def test_fetch_tags_empty(self, mock_run):
        """Test fetching tags when repo has no tags."""
        mock_run.return_value = MagicMock(
            stdout=json.dumps([]),
            returncode=0,
        )

        tags = fetch_versions.fetch_tags("actions", "some-repo")

        self.assertEqual(len(tags), 0)

    @patch("fetch_versions.subprocess.run")
    def test_fetch_tags_api_error(self, mock_run):
        """Test handling API error response."""
        mock_run.return_value = MagicMock(
            stdout='{"message": "API rate limit exceeded"}',
            returncode=0,
        )

        tags = fetch_versions.fetch_tags("actions", "some-repo")

        self.assertEqual(len(tags), 0)


class TestMain(unittest.TestCase):
    """Integration tests for the main function."""

    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_main_integration(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
    ):
        """Test the main function with mocked dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-populate ledger with well-aged semver entries.
            Path(tmpdir, "seen-versions.json").write_text(json.dumps({
                "actions/setup-python": {"v5.0.0": {"sha": "sha5", "first_seen": "2000-01-01"}},
                "actions/setup-node": {"v4.0.0": {"sha": "sha4", "first_seen": "2000-01-01"}},
            }))

            # Mock fetch_repos to return test data
            mock_fetch_repos.return_value = [
                {"name": "setup-python"},
                {"name": "setup-node"},
                {"name": "no-tags-repo"},
            ]

            # Mock fetch_tags to return tags for each repo
            def fetch_tags_side_effect(org, repo_name):
                if repo_name == "setup-python":
                    return [("v5", "sha5"), ("v5.0.0", "sha5"), ("v2.0.0", "sha2")]
                elif repo_name == "setup-node":
                    return [("v4", "sha4"), ("v4.0.0", "sha4"), ("v3.0.0", "sha3")]
                else:
                    return []  # no-tags-repo has no tags

            mock_fetch_tags.side_effect = fetch_tags_side_effect

            fake_dt = MagicMock()
            fake_dt.now.return_value = datetime(2026, 5, 29, tzinfo=timezone.utc)
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", []), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "datetime", fake_dt), \
                 patch.object(fetch_versions, "update_readme"), \
                 patch.object(fetch_versions, "update_readme_sha"):
                fetch_versions.main()

            # Verify the versions file was written correctly
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 2)
            self.assertIn("actions/setup-node@v4.0.0", lines)
            self.assertIn("actions/setup-python@v5.0.0", lines)

            # Verify alphabetical ordering (setup-node before setup-python)
            self.assertEqual(lines[0], "actions/setup-node@v4.0.0")
            self.assertEqual(lines[1], "actions/setup-python@v5.0.0")

            # Verify unversioned repos were saved
            unversioned_file = Path(tmpdir) / "unversioned.txt"
            unversioned_content = unversioned_file.read_text()
            self.assertIn("actions/no-tags-repo", unversioned_content)

    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_main_skips_cached_unversioned(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
    ):
        """Test that cached unversioned repos are skipped."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-populate the unversioned cache
            unversioned_file = Path(tmpdir) / "unversioned.txt"
            unversioned_file.write_text("actions/cached-no-tags\n")

            # Mock fetch_repos to return test data including cached repo
            mock_fetch_repos.return_value = [
                {"name": "setup-python"},
                {"name": "cached-no-tags"},
            ]

            # Mock fetch_tags - should only be called for setup-python
            mock_fetch_tags.return_value = [("v1", "sha1"), ("v5", "sha5")]

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(fetch_versions, "ADDITIONAL_ORGS", []):
                    with patch.object(fetch_versions, "ADDITIONAL_REPOS", []):
                        fetch_versions.main()

            # fetch_tags should only be called once (for setup-python, not cached-no-tags)
            self.assertEqual(mock_fetch_tags.call_count, 1)
            mock_fetch_tags.assert_called_with("actions", "setup-python")

    @patch("fetch_versions.create_regression_issue")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_regression_compared_against_previous_run(
        self, mock_fetch_repos, mock_fetch_tags, mock_issue
    ):
        """A repo versioned last run but now tagless is flagged as a regression."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Previous run had this repo versioned.
            (tmp / "versions.txt").write_text("actions/setup-foo@v1\n")
            mock_fetch_repos.return_value = [{"name": "setup-foo"}]
            mock_fetch_tags.return_value = []  # now no tags -> unversioned
            with patch.object(fetch_versions, "SCRIPT_DIR", tmp), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", []), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "SKIP_REPOS", []):
                fetch_versions.main()
            mock_issue.assert_called_once_with("actions/setup-foo")


class TestVersionPatternMatching(unittest.TestCase):
    """Tests for the version tag pattern matching."""

    def test_valid_version_tags(self):
        """Test that valid vINTEGER tags are matched."""
        import re

        pattern = re.compile(r"^v(\d+)$")

        valid_tags = ["v1", "v2", "v10", "v100", "v999"]
        for tag in valid_tags:
            self.assertIsNotNone(pattern.match(tag), f"{tag} should match")

    def test_invalid_version_tags(self):
        """Test that invalid tags are not matched."""
        import re

        pattern = re.compile(r"^v(\d+)$")

        invalid_tags = [
            "v1.0",
            "v1.0.0",
            "v1-beta",
            "1.0",
            "release-1",
            "v",
            "v1a",
            "V1",  # uppercase
            " v1",  # leading space
            "v1 ",  # trailing space
        ]
        for tag in invalid_tags:
            self.assertIsNone(pattern.match(tag), f"{tag} should not match")


class TestParseRepo(unittest.TestCase):
    """Tests for the parse_repo function."""

    def test_parse_repo_valid(self):
        """Test parsing valid org/repo format."""
        org, repo_name = fetch_versions.parse_repo("actions/setup-python")
        self.assertEqual(org, "actions")
        self.assertEqual(repo_name, "setup-python")

    def test_parse_repo_different_org(self):
        """Test parsing from a different organization."""
        org, repo_name = fetch_versions.parse_repo("docker/build-push-action")
        self.assertEqual(org, "docker")
        self.assertEqual(repo_name, "build-push-action")

    def test_parse_repo_invalid_empty(self):
        """Test parsing empty string."""
        with self.assertRaises(ValueError):
            fetch_versions.parse_repo("")

    def test_parse_repo_invalid_missing_org(self):
        """Test parsing invalid format (missing org)."""
        with self.assertRaises(ValueError):
            fetch_versions.parse_repo("setup-python")

    def test_parse_repo_invalid_too_many_parts(self):
        """Test parsing invalid format (too many parts)."""
        with self.assertRaises(ValueError):
            fetch_versions.parse_repo("org/repo/extra")


class TestUnversionedCache(unittest.TestCase):
    """Tests for the unversioned repos caching functions."""

    def test_load_unversioned_with_repos(self):
        """Test loading unversioned repos from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            unversioned_file = Path(tmpdir) / "unversioned.txt"
            unversioned_file.write_text("repo1\nrepo2\nrepo3\n")

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                result = fetch_versions.load_unversioned()
                self.assertEqual(result, {"repo1", "repo2", "repo3"})

    def test_load_unversioned_file_not_exists(self):
        """Test loading when unversioned.txt doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                result = fetch_versions.load_unversioned()
                self.assertEqual(result, set())

    def test_save_unversioned(self):
        """Test saving unversioned repos to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                fetch_versions.save_unversioned({"zebra", "alpha", "mango"})

                unversioned_file = Path(tmpdir) / "unversioned.txt"
                content = unversioned_file.read_text()
                lines = content.strip().split("\n")
                # Should be sorted alphabetically
                self.assertEqual(lines, ["alpha", "mango", "zebra"])


class TestSemverFallback(unittest.TestCase):
    """Tests for semantic version fallback functionality."""

    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_semver_fallback_no_vinteger(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
    ):
        """Test that a repo with only semver tags (no vINTEGER) is still versioned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-populate ledger with well-aged semver entries.
            Path(tmpdir, "seen-versions.json").write_text(json.dumps({
                "actions/setup-ruby": {
                    "v1.4.0": {"sha": "sha1", "first_seen": "2000-01-01"},
                    "v1.5.0": {"sha": "sha2", "first_seen": "2000-01-01"},
                    "v1.5.1": {"sha": "sha3", "first_seen": "2000-01-01"},
                },
            }))

            # Mock fetch_repos to return a repo with only semver tags
            mock_fetch_repos.return_value = [{"name": "setup-ruby"}]

            # Mock fetch_tags to return semver tags only (no vINTEGER)
            mock_fetch_tags.return_value = [
                ("v1.4.0", "sha1"),
                ("v1.5.0", "sha2"),
                ("v1.5.1", "sha3"),
            ]

            fake_dt = MagicMock()
            fake_dt.now.return_value = datetime(2026, 5, 29, tzinfo=timezone.utc)
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", []), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "datetime", fake_dt), \
                 patch.object(fetch_versions, "update_readme"), \
                 patch.object(fetch_versions, "update_readme_sha"):
                fetch_versions.main()

            # Verify the latest semver tag was selected
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0], "actions/setup-ruby@v1.5.1")

            # Verify SHA-pinned version was also created
            versions_sha_file = Path(tmpdir) / "versions-sha.txt"
            sha_content = versions_sha_file.read_text()
            self.assertIn("actions/setup-ruby@sha3 # v1.5.1", sha_content)

            # Verify repo was NOT marked as unversioned
            unversioned_file = Path(tmpdir) / "unversioned.txt"
            unversioned_content = unversioned_file.read_text()
            self.assertNotIn("actions/setup-ruby", unversioned_content)

    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_highest_semver_selected(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
    ):
        """Test that the highest aged semver tag is selected when multiple exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-populate ledger with well-aged semver entries.
            Path(tmpdir, "seen-versions.json").write_text(json.dumps({
                "actions/setup-node": {
                    "v1.0.0": {"sha": "sha1", "first_seen": "2000-01-01"},
                    "v2.1.0": {"sha": "sha2", "first_seen": "2000-01-01"},
                    "v3.5.2": {"sha": "sha3", "first_seen": "2000-01-01"},
                },
            }))

            # Mock fetch_repos
            mock_fetch_repos.return_value = [{"name": "setup-node"}]

            # Mock fetch_tags - has both vINTEGER and semver
            mock_fetch_tags.return_value = [
                ("v1", "sha1"),
                ("v1.0.0", "sha1"),
                ("v2", "sha2"),
                ("v2.1.0", "sha2"),
                ("v3", "sha3"),
                ("v3.5.2", "sha3"),
            ]

            fake_dt = MagicMock()
            fake_dt.now.return_value = datetime(2026, 5, 29, tzinfo=timezone.utc)
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", []), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "datetime", fake_dt), \
                 patch.object(fetch_versions, "update_readme"), \
                 patch.object(fetch_versions, "update_readme_sha"):
                fetch_versions.main()

            # Verify the highest semver was selected
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0], "actions/setup-node@v3.5.2")

    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_no_version_tags_marks_unversioned(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
    ):
        """Test that repos with no version tags are still marked as unversioned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock fetch_repos
            mock_fetch_repos.return_value = [{"name": "no-tags-repo"}]

            # No tags at all
            mock_fetch_tags.return_value = []

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(fetch_versions, "ADDITIONAL_ORGS", []):
                    with patch.object(fetch_versions, "ADDITIONAL_REPOS", []):
                        fetch_versions.main()

            # Verify repo was marked as unversioned
            unversioned_file = Path(tmpdir) / "unversioned.txt"
            unversioned_content = unversioned_file.read_text()
            self.assertIn("actions/no-tags-repo", unversioned_content)

            # Verify no versions were written
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            self.assertEqual(content.strip(), "")


class TestSkipRepos(unittest.TestCase):
    """Tests for skipping repos from ORG_NAME."""

    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_skip_repos_filters_out_specified_repos(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
    ):
        """Test that repos in SKIP_REPOS are not processed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-populate ledger with well-aged semver entries.
            Path(tmpdir, "seen-versions.json").write_text(json.dumps({
                "actions/setup-python": {"v5.0.0": {"sha": "sha5", "first_seen": "2000-01-01"}},
                "actions/setup-node": {"v5.0.0": {"sha": "sha5", "first_seen": "2000-01-01"}},
            }))

            # Mock fetch_repos to return multiple repos
            mock_fetch_repos.return_value = [
                {"name": "setup-python"},
                {"name": "setup-node"},
                {"name": "skip-me"},
                {"name": "also-skip"},
            ]

            # Mock fetch_tags and version tags
            mock_fetch_tags.return_value = [("v5", "sha5"), ("v5.0.0", "sha5")]

            fake_dt = MagicMock()
            fake_dt.now.return_value = datetime(2026, 5, 29, tzinfo=timezone.utc)
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", []), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "datetime", fake_dt), \
                 patch.object(fetch_versions, "update_readme"), \
                 patch.object(fetch_versions, "update_readme_sha"), \
                 patch.object(fetch_versions, "SKIP_REPOS", ["skip-me", "also-skip"]):
                fetch_versions.main()

            # Verify only non-skipped repos are in versions.txt
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 2)
            self.assertIn("actions/setup-python@v5.0.0", lines)
            self.assertIn("actions/setup-node@v5.0.0", lines)
            self.assertNotIn("actions/skip-me", content)
            self.assertNotIn("actions/also-skip", content)

            # Verify skipped repos were not cached as unversioned
            unversioned_file = Path(tmpdir) / "unversioned.txt"
            unversioned_content = unversioned_file.read_text()
            self.assertNotIn("actions/skip-me", unversioned_content)
            self.assertNotIn("actions/also-skip", unversioned_content)


class TestAdditionalRepos(unittest.TestCase):
    """Tests for additional repos functionality."""

    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_main_with_additional_repos(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
    ):
        """Test main function with additional repos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-populate ledger with well-aged semver entries.
            Path(tmpdir, "seen-versions.json").write_text(json.dumps({
                "actions/setup-python": {"v5.0.0": {"sha": "sha5", "first_seen": "2000-01-01"}},
                "other/some-action": {"v3.0.0": {"sha": "sha3", "first_seen": "2000-01-01"}},
            }))

            # Mock fetch_repos for main org
            mock_fetch_repos.return_value = [{"name": "setup-python"}]

            # Mock fetch_tags responses
            def fetch_tags_side_effect(org, repo_name):
                if org == "actions" and repo_name == "setup-python":
                    return [("v5", "sha5"), ("v5.0.0", "sha5")]
                elif org == "other" and repo_name == "some-action":
                    return [("v3.0.0", "sha3")]
                return []

            mock_fetch_tags.side_effect = fetch_tags_side_effect

            fake_dt = MagicMock()
            fake_dt.now.return_value = datetime(2026, 5, 29, tzinfo=timezone.utc)
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", ["other/some-action"]), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", []), \
                 patch.object(fetch_versions, "datetime", fake_dt), \
                 patch.object(fetch_versions, "update_readme"), \
                 patch.object(fetch_versions, "update_readme_sha"):
                fetch_versions.main()

            # Verify the versions file contains both repos
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 2)
            self.assertIn("actions/setup-python@v5.0.0", lines)
            self.assertIn("other/some-action@v3.0.0", lines)


class TestOrgFileHelpers(unittest.TestCase):
    """Tests for org-specific file helper functions."""

    def test_get_org_versions_file(self):
        """Test getting org-specific versions file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                result = fetch_versions.get_org_versions_file("aws-actions")
                self.assertEqual(result.name, "aws-actions-versions.txt")
                self.assertEqual(result.parent, Path(tmpdir))

    def test_get_org_versions_sha_file(self):
        """Test getting org-specific SHA-pinned versions file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                result = fetch_versions.get_org_versions_sha_file("docker")
                self.assertEqual(result.name, "docker-versions-sha.txt")
                self.assertEqual(result.parent, Path(tmpdir))

    def test_get_org_unversioned_file(self):
        """Test getting org-specific unversioned cache file path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                result = fetch_versions.get_org_unversioned_file("golangci")
                self.assertEqual(result.name, "golangci-unversioned.txt")
                self.assertEqual(result.parent, Path(tmpdir))

    def test_org_files_use_lowercase_names(self):
        """Mixed-case org names (e.g. Azure) must map to lowercase file names,
        matching the URLs generated in index.json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                self.assertEqual(
                    fetch_versions.get_org_versions_file("Azure").name,
                    "azure-versions.txt",
                )
                self.assertEqual(
                    fetch_versions.get_org_versions_sha_file("Azure").name,
                    "azure-versions-sha.txt",
                )
                self.assertEqual(
                    fetch_versions.get_org_unversioned_file("Azure").name,
                    "azure-unversioned.txt",
                )

    def test_get_org_readme_markers(self):
        """Test getting org-specific README markers."""
        start, end = fetch_versions.get_org_readme_markers("aws-actions")
        self.assertEqual(start, "<!-- AWS-ACTIONS_VERSIONS_START -->")
        self.assertEqual(end, "<!-- AWS-ACTIONS_VERSIONS_END -->")

    def test_get_org_readme_sha_markers(self):
        """Test getting org-specific SHA README markers."""
        start, end = fetch_versions.get_org_readme_sha_markers("docker")
        self.assertEqual(start, "<!-- DOCKER_VERSIONS_SHA_START -->")
        self.assertEqual(end, "<!-- DOCKER_VERSIONS_SHA_END -->")


class TestOrgUnversionedCache(unittest.TestCase):
    """Tests for org-specific unversioned repos caching functions."""

    def test_load_org_unversioned_file_not_exists(self):
        """Test loading when org-specific unversioned file doesn't exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                result = fetch_versions.load_org_unversioned("aws-actions")
                self.assertEqual(result, set())

    def test_load_org_unversioned_with_repos(self):
        """Test loading org-specific unversioned repos from file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                unversioned_file = Path(tmpdir) / "aws-actions-unversioned.txt"
                unversioned_file.write_text("aws-actions/repo1\naws-actions/repo2\n")

                result = fetch_versions.load_org_unversioned("aws-actions")
                self.assertEqual(result, {"aws-actions/repo1", "aws-actions/repo2"})

    def test_save_org_unversioned(self):
        """Test saving org-specific unversioned repos to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                fetch_versions.save_org_unversioned(
                    "docker", {"docker/repo3", "docker/repo1", "docker/repo2"}
                )

                unversioned_file = Path(tmpdir) / "docker-unversioned.txt"
                content = unversioned_file.read_text()
                lines = content.strip().split("\n")
                # Should be sorted alphabetically
                self.assertEqual(
                    lines, ["docker/repo1", "docker/repo2", "docker/repo3"]
                )


class TestOrgReadmeUpdates(unittest.TestCase):
    """Tests for org-specific README update functions."""

    def test_update_readme_for_org_new_section(self):
        """Test updating README with new org section (markers don't exist)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_file = Path(tmpdir) / "README.md"
            readme_file.write_text("# My README\n\nSome content\n")

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                fetch_versions.update_readme_for_org(
                    "aws-actions", "aws-actions/configure-aws-credentials@v4\n"
                )

            content = readme_file.read_text()
            self.assertIn("<!-- AWS-ACTIONS_VERSIONS_START -->", content)
            self.assertIn("<!-- AWS-ACTIONS_VERSIONS_END -->", content)
            self.assertIn("<details>", content)
            self.assertIn(
                "<summary><h3><code>aws-actions</code></h3></summary>", content
            )
            self.assertIn("aws-actions/configure-aws-credentials@v4", content)

    def test_update_readme_for_org_existing_section(self):
        """Test updating README when org section already exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_file = Path(tmpdir) / "README.md"
            initial_content = """# My README

<!-- AWS-ACTIONS_VERSIONS_START -->
<details>
<summary>aws-actions</summary>

## aws-actions actions

```
aws-actions/old@v1
```

</details>
<!-- AWS-ACTIONS_VERSIONS_END -->
"""
            readme_file.write_text(initial_content)

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                fetch_versions.update_readme_for_org(
                    "aws-actions", "aws-actions/new@v2\n"
                )

            content = readme_file.read_text()
            # Should have replaced the old content
            self.assertNotIn("aws-actions/old@v1", content)
            self.assertIn("aws-actions/new@v2", content)
            # Should only have one set of markers
            self.assertEqual(content.count("<!-- AWS-ACTIONS_VERSIONS_START -->"), 1)
            self.assertEqual(content.count("<!-- AWS-ACTIONS_VERSIONS_END -->"), 1)

    def test_update_readme_sha_for_org_new_section(self):
        """Test updating README with new org SHA section (markers don't exist)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            readme_file = Path(tmpdir) / "README.md"
            readme_file.write_text("# My README\n\nSome content\n")

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                fetch_versions.update_readme_sha_for_org(
                    "docker", "docker/login-action@abc123 # v4.0.0\n"
                )

            content = readme_file.read_text()
            self.assertIn("<!-- DOCKER_VERSIONS_SHA_START -->", content)
            self.assertIn("<!-- DOCKER_VERSIONS_SHA_END -->", content)
            self.assertIn("<details>", content)
            self.assertIn(
                "<summary><h3><code>docker</code> (SHA-pinned)</h3></summary>",
                content,
            )
            self.assertIn("docker/login-action@abc123 # v4.0.0", content)


class TestAdditionalOrgs(unittest.TestCase):
    """Tests for additional orgs functionality in main()."""

    @patch("fetch_versions.is_action_repo", return_value=True)
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_main_with_additional_orgs(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_is_action,
    ):
        """Test main function with additional orgs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Pre-populate ledger with well-aged semver entries.
            Path(tmpdir, "seen-versions.json").write_text(json.dumps({
                "actions/setup-python": {"v5.0.0": {"sha": "sha5", "first_seen": "2000-01-01"}},
                "aws-actions/configure-aws-credentials": {
                    "v4.0.0": {"sha": "sha4", "first_seen": "2000-01-01"},
                },
            }))

            # Mock fetch_repos to return test data for main org and additional orgs
            def fetch_repos_side_effect(org):
                if org == "actions":
                    return [{"name": "setup-python"}]
                elif org == "aws-actions":
                    return [{"name": "configure-aws-credentials"}]
                return []

            mock_fetch_repos.side_effect = fetch_repos_side_effect

            # Mock fetch_tags to return tags for each repo
            def fetch_tags_side_effect(org, repo_name):
                if org == "actions" and repo_name == "setup-python":
                    return [("v5", "sha5"), ("v5.0.0", "sha5")]
                elif org == "aws-actions" and repo_name == "configure-aws-credentials":
                    return [("v4", "sha4"), ("v4.0.0", "sha4")]
                return []

            mock_fetch_tags.side_effect = fetch_tags_side_effect

            fake_dt = MagicMock()
            fake_dt.now.return_value = datetime(2026, 5, 29, tzinfo=timezone.utc)
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", ["aws-actions"]), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "datetime", fake_dt), \
                 patch.object(fetch_versions, "update_readme"), \
                 patch.object(fetch_versions, "update_readme_sha"):
                fetch_versions.main()

            # Verify the main versions file contains only actions org repos (not from ADDITIONAL_ORGS)
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")
            self.assertEqual(len(lines), 1)
            self.assertIn("actions/setup-python@v5.0.0", lines)
            self.assertNotIn("aws-actions/configure-aws-credentials", content)

            # Verify the org-specific versions file contains only aws-actions repos
            aws_versions_file = Path(tmpdir) / "aws-actions-versions.txt"
            aws_content = aws_versions_file.read_text()
            aws_lines = aws_content.strip().split("\n")
            self.assertEqual(len(aws_lines), 1)
            self.assertEqual(aws_lines[0], "aws-actions/configure-aws-credentials@v4.0.0")


class TestIndexJson(unittest.TestCase):
    """Tests for index.json generation."""

    @patch("fetch_versions.get_base_url")
    def test_generate_index_json_structure(self, mock_base_url):
        """Test that index.json has correct structure."""
        mock_base_url.return_value = "https://example.com/"

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(
                    fetch_versions, "ADDITIONAL_ORGS", ["aws-actions"]
                ):
                    fetch_versions.generate_index_json()

            index_file = Path(tmpdir) / "index.json"
            self.assertTrue(index_file.exists())

            with open(index_file) as f:
                index = json.load(f)

            # Verify structure
            self.assertIn("bundles", index)
            self.assertIn("orgs", index)
            self.assertIn("default", index["bundles"])
            self.assertIn("aws-actions", index["orgs"])

    @patch("fetch_versions.get_base_url")
    def test_index_json_urls_correct(self, mock_base_url):
        """Test that URLs are constructed correctly."""
        mock_base_url.return_value = "https://michael-k.github.io/quarantined-actions/"

        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(
                    fetch_versions, "ADDITIONAL_ORGS", ["aws-actions", "docker"]
                ):
                    fetch_versions.generate_index_json()

            index_file = Path(tmpdir) / "index.json"
            with open(index_file) as f:
                index = json.load(f)

            # Verify default bundle URLs
            self.assertEqual(
                index["bundles"]["default"]["versions_url"],
                "https://michael-k.github.io/quarantined-actions/versions.txt",
            )
            self.assertEqual(
                index["bundles"]["default"]["versions_sha_url"],
                "https://michael-k.github.io/quarantined-actions/versions-sha.txt",
            )

            # Verify org URLs
            self.assertEqual(
                index["orgs"]["aws-actions"]["versions_url"],
                "https://michael-k.github.io/quarantined-actions/aws-actions-versions.txt",
            )
            self.assertEqual(
                index["orgs"]["docker"]["versions_sha_url"],
                "https://michael-k.github.io/quarantined-actions/docker-versions-sha.txt",
            )

    @patch("fetch_versions.subprocess.run")
    def test_get_base_url_from_git(self, mock_run):
        """Test that base URL is derived from git config."""
        mock_run.return_value = MagicMock(
            stdout="https://github.com/michael-k/quarantined-actions.git",
            returncode=0,
        )

        result = fetch_versions.get_base_url()

        self.assertEqual(result, "https://michael-k.github.io/quarantined-actions/")

    @patch("fetch_versions.subprocess.run")
    def test_get_base_url_fallback(self, mock_run):
        """Test that base URL falls back to default when git config fails."""
        mock_run.return_value = MagicMock(stdout="", returncode=1)

        result = fetch_versions.get_base_url()

        self.assertEqual(result, "https://michael-k.github.io/quarantined-actions/")


class TestDetectRegressions(unittest.TestCase):
    """Tests for the detect_regressions function."""

    def test_no_regressions_same_sets(self):
        """No regressions when old and new are identical."""
        old = {"actions/repo-a", "actions/repo-b"}
        new = {"actions/repo-a", "actions/repo-b"}
        result = fetch_versions.detect_regressions(old, new, {}, {})
        self.assertEqual(result, [])

    def test_simple_regression(self):
        """One repo added to unversioned is a regression."""
        old: set[str] = set()
        new = {"actions/repo-a"}
        result = fetch_versions.detect_regressions(old, new, {}, {})
        self.assertEqual(result, ["actions/repo-a"])

    def test_multiple_regressions_sorted(self):
        """Multiple regressions returned as sorted list."""
        old: set[str] = set()
        new = {"actions/zebra", "actions/alpha", "actions/middle"}
        result = fetch_versions.detect_regressions(old, new, {}, {})
        self.assertEqual(result, ["actions/alpha", "actions/middle", "actions/zebra"])

    def test_already_unversioned_not_regression(self):
        """Repo already in old unversioned set is NOT a regression."""
        old = {"actions/repo-a"}
        new = {"actions/repo-a", "actions/repo-b"}
        result = fetch_versions.detect_regressions(old, new, {}, {})
        self.assertEqual(result, ["actions/repo-b"])

    def test_org_specific_regressions(self):
        """Org-specific regressions detected correctly."""
        old_org = {"aws-actions": {"aws-actions/cached"}}
        new_org = {"aws-actions": {"aws-actions/cached", "aws-actions/new-regression"}}
        result = fetch_versions.detect_regressions(set(), set(), old_org, new_org)
        self.assertEqual(result, ["aws-actions/new-regression"])

    def test_org_regression_with_main_regression(self):
        """Both main and org regressions detected together."""
        old: set[str] = set()
        new = {"actions/main-regression"}
        old_org: dict[str, set[str]] = {}
        new_org = {"aws-actions": {"aws-actions/org-regression"}}
        result = fetch_versions.detect_regressions(old, new, old_org, new_org)
        self.assertEqual(
            result,
            ["actions/main-regression", "aws-actions/org-regression"],
        )

    def test_empty_inputs(self):
        """Empty inputs produce no regressions."""
        result = fetch_versions.detect_regressions(set(), set(), {}, {})
        self.assertEqual(result, [])

    def test_old_versioned_filters_false_positive(self):
        """Repos not in old_versioned are excluded even if in new unversioned."""
        old: set[str] = set()
        new = {"actions/repo-a", "actions/repo-b"}
        old_versioned = {"actions/repo-a"}
        result = fetch_versions.detect_regressions(
            old, new, {}, {}, old_versioned
        )
        self.assertEqual(result, ["actions/repo-a"])

    def test_old_versioned_none_no_filter(self):
        """When old_versioned is None, no filtering is applied."""
        old: set[str] = set()
        new = {"actions/repo-a", "actions/repo-b"}
        result = fetch_versions.detect_regressions(old, new, {}, {}, None)
        self.assertEqual(result, ["actions/repo-a", "actions/repo-b"])

    def test_old_versioned_filters_org_regression(self):
        """Org repos not in old_versioned are excluded."""
        old_org: dict[str, set[str]] = {}
        new_org = {"aws-actions": {"aws-actions/repo-a", "aws-actions/repo-b"}}
        old_versioned = {"aws-actions/repo-a"}
        result = fetch_versions.detect_regressions(
            set(), set(), old_org, new_org, old_versioned
        )
        self.assertEqual(result, ["aws-actions/repo-a"])


class TestLoadVersionedRepos(unittest.TestCase):
    """Tests for the load_versioned_repos function."""

    def test_load_from_single_file(self):
        """Test loading versioned repos from a single file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            versions_file = Path(tmpdir) / "versions.txt"
            versions_file.write_text("actions/setup-python@v5\nactions/checkout@v6\n")
            result = fetch_versions.load_versioned_repos(versions_file)
            self.assertEqual(result, {"actions/setup-python", "actions/checkout"})

    def test_load_from_multiple_files(self):
        """Test loading versioned repos from multiple files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            versions_file = Path(tmpdir) / "versions.txt"
            org_file = Path(tmpdir) / "aws-actions-versions.txt"
            versions_file.write_text("actions/setup-python@v5\n")
            org_file.write_text("aws-actions/configure-aws-credentials@v6\n")
            result = fetch_versions.load_versioned_repos(versions_file, org_file)
            self.assertEqual(
                result,
                {"actions/setup-python", "aws-actions/configure-aws-credentials"},
            )

    def test_load_missing_file(self):
        """Test loading when file doesn't exist."""
        result = fetch_versions.load_versioned_repos(Path("/nonexistent/versions.txt"))
        self.assertEqual(result, set())

    def test_load_empty_file(self):
        """Test loading from an empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            versions_file = Path(tmpdir) / "versions.txt"
            versions_file.write_text("")
            result = fetch_versions.load_versioned_repos(versions_file)
            self.assertEqual(result, set())


class TestReportRegression(unittest.TestCase):
    """Tests for the report_regression function."""

    def test_report_regression_outputs_to_stderr(self):
        """report_regression prints regression details to stderr."""
        with tempfile.TemporaryDirectory() as tmpdir:
            import io

            stderr_capture = io.StringIO()
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch("sys.stderr", stderr_capture):
                    fetch_versions.report_regression("actions/repo-a")

            output = stderr_capture.getvalue()
            self.assertIn("REGRESSION: actions/repo-a", output)
            self.assertIn("previously versioned", output)
            self.assertIn(
                f"{fetch_versions.GITHUB_API_URL}/repos/actions/repo-a/tags", output
            )

    def test_report_regression_transient_hint(self):
        """report_regression mentions transient issues."""
        import io

        stderr_capture = io.StringIO()
        with patch("sys.stderr", stderr_capture):
            fetch_versions.report_regression("docker/build-push-action")

        output = stderr_capture.getvalue()
        self.assertIn("transient", output)


class TestCreateRegressionIssue(unittest.TestCase):
    """Tests for the create_regression_issue function."""

    @patch("fetch_versions.subprocess.run")
    def test_not_in_ci_reports_regression(self, mock_run):
        """When GITHUB_ACTIONS is not set, regression is reported to stderr."""
        import io

        stderr_capture = io.StringIO()
        with patch.dict("os.environ", {}, clear=True):
            with patch("sys.stderr", stderr_capture):
                fetch_versions.create_regression_issue("actions/repo-a")
        mock_run.assert_not_called()
        output = stderr_capture.getvalue()
        self.assertIn("REGRESSION: actions/repo-a", output)

    @patch("fetch_versions.subprocess.run")
    def test_not_true_reports_regression(self, mock_run):
        """When GITHUB_ACTIONS is not 'true', regression is reported to stderr."""
        import io

        stderr_capture = io.StringIO()
        with patch.dict("os.environ", {"GITHUB_ACTIONS": "false"}):
            with patch("sys.stderr", stderr_capture):
                fetch_versions.create_regression_issue("actions/repo-a")
        mock_run.assert_not_called()
        output = stderr_capture.getvalue()
        self.assertIn("REGRESSION: actions/repo-a", output)

    @patch("fetch_versions.subprocess.run")
    def test_ci_gate_creates_issue(self, mock_run):
        """When in CI with no existing issue, creates issue and label."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "user/repo",
            "GITHUB_RUN_ID": "12345",
        }
        with patch.dict("os.environ", env):
            # First call: gh issue list (no existing issues)
            # Second call: gh label create
            # Third call: gh issue create
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            fetch_versions.create_regression_issue("actions/repo-a")

        self.assertEqual(mock_run.call_count, 3)

        # Verify issue list check
        list_call = mock_run.call_args_list[0]
        self.assertEqual(list_call[0][0][0:3], ["gh", "issue", "list"])
        self.assertIn("--label", list_call[0][0])
        self.assertIn("regression", list_call[0][0])

        # Verify label create
        label_call = mock_run.call_args_list[1]
        self.assertEqual(label_call[0][0][0:3], ["gh", "label", "create"])

        # Verify issue create
        create_call = mock_run.call_args_list[2]
        self.assertEqual(create_call[0][0][0:3], ["gh", "issue", "create"])
        title_idx = create_call[0][0].index("--title")
        self.assertEqual(
            create_call[0][0][title_idx + 1],
            "Regression: actions/repo-a moved to unversioned",
        )

    @patch("fetch_versions.subprocess.run")
    def test_idempotency_skips_existing_issue(self, mock_run):
        """When an open regression issue exists, no new issue is created."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "user/repo",
            "GITHUB_RUN_ID": "12345",
        }
        with patch.dict("os.environ", env):
            # gh issue list returns existing issue
            mock_run.return_value = MagicMock(
                stdout="42\topen\tRegression: actions/repo-a moved to unversioned",
                returncode=0,
            )
            fetch_versions.create_regression_issue("actions/repo-a")

        # Only the list call should be made
        self.assertEqual(mock_run.call_count, 1)

    @patch("fetch_versions.subprocess.run")
    def test_error_resilience(self, mock_run):
        """If gh fails, function returns without raising."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "user/repo",
            "GITHUB_RUN_ID": "12345",
        }
        with patch.dict("os.environ", env):
            mock_run.side_effect = subprocess.CalledProcessError(1, "gh")
            # Should not raise
            fetch_versions.create_regression_issue("actions/repo-a")

    @patch("fetch_versions.subprocess.run")
    def test_issue_body_contains_workflow_link(self, mock_run):
        """Issue body includes workflow run link when CI env vars are set."""
        env = {
            "GITHUB_ACTIONS": "true",
            "GITHUB_SERVER_URL": "https://github.com",
            "GITHUB_REPOSITORY": "user/repo",
            "GITHUB_RUN_ID": "12345",
        }
        with patch.dict("os.environ", env):
            mock_run.return_value = MagicMock(stdout="", returncode=0)
            fetch_versions.create_regression_issue("actions/repo-a")

        create_call = mock_run.call_args_list[2]
        body_idx = create_call[0][0].index("--body")
        body = create_call[0][0][body_idx + 1]
        self.assertIn(
            "https://github.com/user/repo/actions/runs/12345", body
        )


class TestFetchReposBySearch(unittest.TestCase):
    @patch("fetch_versions.subprocess.run")
    def test_single_page(self, mock_run):
        payload = {"total_count": 2, "items": [
            {"name": "a", "full_name": "docker/a"},
            {"name": "b", "full_name": "docker/b"},
        ]}
        mock_run.return_value = MagicMock(stdout=json.dumps(payload), returncode=0)
        repos = fetch_versions.fetch_repos_by_search("org:docker topic:github-actions")
        self.assertEqual([r["full_name"] for r in repos], ["docker/a", "docker/b"])

    @patch("fetch_versions.subprocess.run")
    def test_pagination(self, mock_run):
        page1 = {"items": [{"name": f"r{i}", "full_name": f"docker/r{i}"}
                           for i in range(100)]}
        page2 = {"items": [{"name": "last", "full_name": "docker/last"}]}
        mock_run.side_effect = [
            MagicMock(stdout=json.dumps(page1), returncode=0),
            MagicMock(stdout=json.dumps(page2), returncode=0),
        ]
        repos = fetch_versions.fetch_repos_by_search("q")
        self.assertEqual(len(repos), 101)

    @patch("fetch_versions.subprocess.run")
    def test_api_error_returns_empty(self, mock_run):
        mock_run.return_value = MagicMock(
            stdout='{"message": "API rate limit exceeded"}', returncode=0)
        self.assertEqual(fetch_versions.fetch_repos_by_search("q"), [])


class TestIsActionRepo(unittest.TestCase):
    @patch("fetch_versions.subprocess.run")
    def test_action_yml_present(self, mock_run):
        mock_run.return_value = MagicMock(stdout="200", returncode=0)
        self.assertTrue(fetch_versions.is_action_repo("docker", "build-push-action"))

    @patch("fetch_versions.subprocess.run")
    def test_neither_present(self, mock_run):
        mock_run.return_value = MagicMock(stdout="404", returncode=0)
        self.assertFalse(fetch_versions.is_action_repo("docker", "actions-toolkit"))

    @patch("fetch_versions.subprocess.run")
    def test_action_yaml_fallback(self, mock_run):
        mock_run.side_effect = [
            MagicMock(stdout="404", returncode=0),  # action.yml
            MagicMock(stdout="200", returncode=0),  # action.yaml
        ]
        self.assertTrue(fetch_versions.is_action_repo("some", "repo"))


class TestOrgBundles(unittest.TestCase):
    @patch("fetch_versions.is_action_repo")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos_by_search")
    @patch("fetch_versions.fetch_repos")
    def test_search_bundle_filters_non_actions(
        self, mock_fetch_repos, mock_search, mock_tags, mock_is_action
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Aged ledger entry so the version clears quarantine.
            (tmp / "seen-versions.json").write_text(json.dumps({
                "docker/build-push-action": {
                    "v1.0.0": {"sha": "sha1", "first_seen": "2000-01-01"},
                }}))
            mock_fetch_repos.return_value = []
            mock_search.return_value = [
                {"name": "build-push-action",
                 "full_name": "docker/build-push-action"},
                {"name": "actions-toolkit", "full_name": "docker/actions-toolkit"},
            ]
            mock_tags.return_value = [("v1", "sha1"), ("v1.0.0", "sha1")]
            mock_is_action.side_effect = lambda org, repo: repo == "build-push-action"
            with patch.object(fetch_versions, "SCRIPT_DIR", tmp), \
                 patch.object(fetch_versions, "ORG_NAME", "actions"), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", ["docker"]), \
                 patch.object(fetch_versions, "ORG_BUNDLES",
                              {"docker": {"source": "search", "query": "q"}}), \
                 patch.object(fetch_versions, "SKIP_REPOS", []):
                fetch_versions.main()
            docker_versions = (tmp / "docker-versions.txt").read_text()
            self.assertIn("docker/build-push-action@v1.0.0", docker_versions)
            self.assertNotIn("actions-toolkit", docker_versions)
            self.assertNotIn("docker/", (tmp / "versions.txt").read_text())
            mock_search.assert_called_once_with("q")

    @patch("fetch_versions.is_action_repo")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_full_bundle_filters_non_actions(
        self, mock_fetch_repos, mock_tags, mock_is_action
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Aged ledger entry so the version clears quarantine.
            (tmp / "seen-versions.json").write_text(json.dumps({
                "astral-sh/setup-uv": {
                    "v1.0.0": {"sha": "sha1", "first_seen": "2000-01-01"},
                }}))
            def repos(org):
                if org == "astral-sh":
                    return [{"name": "setup-uv"}, {"name": "uv"}]
                return []
            mock_fetch_repos.side_effect = repos
            mock_tags.return_value = [("v1", "sha1"), ("v1.0.0", "sha1")]
            mock_is_action.side_effect = lambda org, repo: repo == "setup-uv"
            with patch.object(fetch_versions, "SCRIPT_DIR", tmp), \
                 patch.object(fetch_versions, "ORG_NAME", "actions"), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", ["astral-sh"]), \
                 patch.object(fetch_versions, "ORG_BUNDLES",
                              {"astral-sh": {"source": "full"}}), \
                 patch.object(fetch_versions, "SKIP_REPOS", []):
                fetch_versions.main()
            astral = (tmp / "astral-sh-versions.txt").read_text()
            self.assertIn("astral-sh/setup-uv@v1.0.0", astral)
            self.assertNotIn("astral-sh/uv", astral)


class TestRefreshMode(unittest.TestCase):
    @patch("fetch_versions.is_action_repo")
    @patch("fetch_versions.fetch_repos_by_search")
    @patch("fetch_versions.fetch_repos")
    @patch("fetch_versions.fetch_tags")
    def test_refresh_uses_tracked_files_and_skips_discovery(
        self, mock_tags, mock_fetch_repos, mock_search, mock_is_action
    ):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "versions.txt").write_text("actions/checkout@v5.0.0\n")
            (tmp / "aws-actions-versions.txt").write_text(
                "aws-actions/configure-aws-credentials@v4.0.0\n")
            # Aged ledger entries so the refreshed versions clear quarantine.
            (tmp / "seen-versions.json").write_text(json.dumps({
                "actions/checkout": {
                    "v6.0.0": {"sha": "sha6", "first_seen": "2000-01-01"},
                },
                "aws-actions/configure-aws-credentials": {
                    "v5.0.0": {"sha": "sha5", "first_seen": "2000-01-01"},
                },
            }))
            def tags(org, repo):
                if repo == "checkout":
                    return [("v6", "sha6"), ("v6.0.0", "sha6")]
                return [("v5", "sha5"), ("v5.0.0", "sha5")]
            mock_tags.side_effect = tags
            with patch.object(fetch_versions, "SCRIPT_DIR", tmp), \
                 patch.object(fetch_versions, "ORG_NAME", "actions"), \
                 patch.object(fetch_versions, "ADDITIONAL_ORGS", ["aws-actions"]), \
                 patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
                 patch.object(fetch_versions, "update_readme"), \
                 patch.object(fetch_versions, "update_readme_sha"), \
                 patch.object(fetch_versions, "update_readme_for_org"), \
                 patch.object(fetch_versions, "update_readme_sha_for_org"):
                fetch_versions.main(discover=False)
            # discovery was skipped entirely
            mock_fetch_repos.assert_not_called()
            mock_search.assert_not_called()
            mock_is_action.assert_not_called()
            # versions refreshed from the tracked set
            self.assertEqual((tmp / "versions.txt").read_text(),
                             "actions/checkout@v6.0.0\n")
            self.assertIn("aws-actions/configure-aws-credentials@v5.0.0",
                          (tmp / "aws-actions-versions.txt").read_text())


class LedgerPathTests(unittest.TestCase):
    def test_get_ledger_file_under_script_dir(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                self.assertEqual(
                    fetch_versions.get_ledger_file(),
                    Path(tmpdir) / "seen-versions.json",
                )

    def test_quarantine_days_constant(self):
        self.assertEqual(fetch_versions.QUARANTINE_DAYS, 14)


class ParseSemverTagsTests(unittest.TestCase):
    def test_returns_only_exact_semver_sorted_descending(self):
        tags = [
            ("v5", "aaa"),          # bare major: excluded (floating)
            ("v4.1.2", "bbb"),
            ("v4.10.0", "ccc"),
            ("v4.2.0", "ddd"),
            ("nightly", "eee"),     # non-semver: excluded
            ("v4.1", "fff"),        # two-part: excluded
        ]
        result = fetch_versions.parse_semver_tags(tags)
        self.assertEqual(
            result,
            [
                ((4, 10, 0), "v4.10.0", "ccc"),
                ((4, 2, 0), "v4.2.0", "ddd"),
                ((4, 1, 2), "v4.1.2", "bbb"),
            ],
        )

    def test_empty_when_no_semver(self):
        self.assertEqual(fetch_versions.parse_semver_tags([("v1", "x")]), [])


class RecordObservationTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 5, 29)

    def test_new_tag_inserted_with_today(self):
        ledger: dict = {}
        poisoned = fetch_versions.record_observation(
            ledger, "actions/checkout", "v5.0.0", "sha1", self.today
        )
        self.assertFalse(poisoned)
        self.assertEqual(
            ledger["actions/checkout"]["v5.0.0"],
            {"sha": "sha1", "first_seen": "2026-05-29"},
        )

    def test_same_sha_keeps_first_seen(self):
        ledger = {"a/b": {"v1.0.0": {"sha": "s", "first_seen": "2026-01-01"}}}
        poisoned = fetch_versions.record_observation(
            ledger, "a/b", "v1.0.0", "s", self.today
        )
        self.assertFalse(poisoned)
        self.assertEqual(ledger["a/b"]["v1.0.0"]["first_seen"], "2026-01-01")

    def test_changed_sha_poisons_and_signals(self):
        ledger = {"a/b": {"v1.0.0": {"sha": "old", "first_seen": "2026-01-01"}}}
        poisoned = fetch_versions.record_observation(
            ledger, "a/b", "v1.0.0", "new", self.today
        )
        self.assertTrue(poisoned)
        self.assertTrue(ledger["a/b"]["v1.0.0"]["bad"])

    def test_already_bad_is_ignored(self):
        ledger = {"a/b": {"v1.0.0": {"sha": "old", "first_seen": "x", "bad": True}}}
        poisoned = fetch_versions.record_observation(
            ledger, "a/b", "v1.0.0", "old", self.today
        )
        self.assertFalse(poisoned)
        self.assertEqual(
            ledger["a/b"]["v1.0.0"],
            {"sha": "old", "first_seen": "x", "bad": True},
        )

    def test_already_bad_with_different_sha_stays_ignored(self):
        ledger = {"a/b": {"v1.0.0": {"sha": "old", "first_seen": "x", "bad": True}}}
        poisoned = fetch_versions.record_observation(
            ledger, "a/b", "v1.0.0", "different", self.today
        )
        self.assertFalse(poisoned)
        self.assertEqual(
            ledger["a/b"]["v1.0.0"],
            {"sha": "old", "first_seen": "x", "bad": True},
        )


class SelectQuarantinedVersionTests(unittest.TestCase):
    def setUp(self):
        self.today = date(2026, 5, 29)  # cutoff = 2026-05-15

    def _upstream(self):
        return [
            ((5, 0, 0), "v5.0.0", "sha5"),
            ((4, 1, 2), "v4.1.2", "sha4"),
        ]

    def test_skips_too_new_picks_older_aged(self):
        ledger = {"a/b": {
            "v5.0.0": {"sha": "sha5", "first_seen": "2026-05-27"},  # 2 days
            "v4.1.2": {"sha": "sha4", "first_seen": "2026-05-01"},  # 28 days
        }}
        self.assertEqual(
            fetch_versions.select_quarantined_version(
                ledger, "a/b", self._upstream(), self.today),
            ("v4.1.2", "sha4"),
        )

    def test_picks_highest_when_both_aged(self):
        ledger = {"a/b": {
            "v5.0.0": {"sha": "sha5", "first_seen": "2026-05-01"},
            "v4.1.2": {"sha": "sha4", "first_seen": "2026-05-01"},
        }}
        self.assertEqual(
            fetch_versions.select_quarantined_version(
                ledger, "a/b", self._upstream(), self.today),
            ("v5.0.0", "sha5"),
        )

    def test_exactly_14_days_is_eligible(self):
        ledger = {"a/b": {"v4.1.2": {"sha": "sha4", "first_seen": "2026-05-15"}}}
        self.assertEqual(
            fetch_versions.select_quarantined_version(
                ledger, "a/b", [((4, 1, 2), "v4.1.2", "sha4")], self.today),
            ("v4.1.2", "sha4"),
        )

    def test_bad_entry_skipped(self):
        ledger = {"a/b": {
            "v5.0.0": {"sha": "sha5", "first_seen": "2026-05-01", "bad": True},
            "v4.1.2": {"sha": "sha4", "first_seen": "2026-05-01"},
        }}
        self.assertEqual(
            fetch_versions.select_quarantined_version(
                ledger, "a/b", self._upstream(), self.today),
            ("v4.1.2", "sha4"),
        )

    def test_sha_mismatch_with_upstream_skipped(self):
        ledger = {"a/b": {"v4.1.2": {"sha": "OLD", "first_seen": "2026-05-01"}}}
        self.assertIsNone(
            fetch_versions.select_quarantined_version(
                ledger, "a/b", [((4, 1, 2), "v4.1.2", "sha4")], self.today))

    def test_none_when_nothing_eligible(self):
        ledger = {"a/b": {"v5.0.0": {"sha": "sha5", "first_seen": "2026-05-28"}}}
        self.assertIsNone(
            fetch_versions.select_quarantined_version(
                ledger, "a/b", [((5, 0, 0), "v5.0.0", "sha5")], self.today))


class LedgerIOTests(unittest.TestCase):
    def test_grandfather_seeds_from_versions_sha_when_absent(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "versions-sha.txt").write_text(
                "actions/checkout@deadbeef # v4.1.2\n"
                "actions/setup-node@cafef00d # v5.0.0\n"
            )
            with patch.object(fetch_versions, "SCRIPT_DIR", tmp):
                with patch.object(fetch_versions, "ADDITIONAL_ORGS", []):
                    ledger = fetch_versions.load_ledger()
        self.assertEqual(
            ledger["actions/checkout"]["v4.1.2"],
            {"sha": "deadbeef", "first_seen": "2000-01-01"},
        )
        self.assertEqual(ledger["actions/setup-node"]["v5.0.0"]["sha"], "cafef00d")

    def test_load_existing_ledger_verbatim(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            payload = {"a/b": {"v1.0.0": {"sha": "s", "first_seen": "2026-01-01"}}}
            (tmp / "seen-versions.json").write_text(json.dumps(payload))
            with patch.object(fetch_versions, "SCRIPT_DIR", tmp):
                self.assertEqual(fetch_versions.load_ledger(), payload)

    def test_save_round_trips_and_sorts(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            ledger = {"b/b": {"v1.0.0": {"sha": "s", "first_seen": "x", "bad": True}},
                      "a/a": {"v2.0.0": {"sha": "t", "first_seen": "y"}}}
            with patch.object(fetch_versions, "SCRIPT_DIR", tmp):
                fetch_versions.save_ledger(ledger)
                reloaded = fetch_versions.load_ledger()
            self.assertEqual(reloaded, ledger)
            text = (tmp / "seen-versions.json").read_text()
            self.assertLess(text.index("a/a"), text.index("b/b"))

    def test_load_ledger_corrupt_json_exits_cleanly(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "seen-versions.json").write_text("{ not valid json")
            with patch.object(fetch_versions, "SCRIPT_DIR", tmp):
                with self.assertRaises(SystemExit) as ctx:
                    fetch_versions.load_ledger()
            self.assertEqual(ctx.exception.code, 1)


class TagMovedIssueTests(unittest.TestCase):
    @patch.dict(os.environ, {}, clear=True)
    @patch("fetch_versions.subprocess.run")
    def test_reports_to_stderr_when_not_in_ci(self, mock_run):
        fetch_versions.create_tag_moved_issue("a/b", "v1.0.0")
        mock_run.assert_not_called()

    @patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True)
    @patch("fetch_versions.subprocess.run")
    def test_creates_issue_in_ci_when_none_exists(self, mock_run):
        mock_run.side_effect = [
            MagicMock(stdout="", returncode=0),   # issue list -> empty
            MagicMock(stdout="", returncode=0),   # label create
            MagicMock(stdout="", returncode=0),   # issue create
        ]
        fetch_versions.create_tag_moved_issue("a/b", "v1.0.0")
        create_call = mock_run.call_args_list[-1].args[0]
        self.assertIn("issue", create_call)
        self.assertIn("create", create_call)
        self.assertIn("tag-moved", create_call)

    @patch.dict(os.environ, {"GITHUB_ACTIONS": "true"}, clear=True)
    @patch("fetch_versions.subprocess.run")
    def test_skips_when_issue_already_open(self, mock_run):
        mock_run.return_value = MagicMock(stdout="#42 existing", returncode=0)
        fetch_versions.create_tag_moved_issue("a/b", "v1.0.0")
        self.assertEqual(mock_run.call_count, 1)


class MainQuarantineTests(unittest.TestCase):
    def _run_main(self, tmp, tags_by_repo, today):
        """Run main() with fetch_repos/fetch_tags/date mocked, in tmp dir."""
        def fake_fetch_repos(org):
            return [{"name": n.split("/", 1)[1]}
                    for n in tags_by_repo if n.startswith(org + "/")]

        def fake_fetch_tags(org, repo_name):
            return tags_by_repo[f"{org}/{repo_name}"]

        fake_dt = MagicMock()
        fake_dt.now.return_value = datetime(today.year, today.month, today.day,
                                            tzinfo=timezone.utc)
        with patch.object(fetch_versions, "SCRIPT_DIR", tmp), \
             patch.object(fetch_versions, "ORG_NAME", "actions"), \
             patch.object(fetch_versions, "ADDITIONAL_ORGS", []), \
             patch.object(fetch_versions, "ADDITIONAL_REPOS", []), \
             patch.object(fetch_versions, "SKIP_REPOS", []), \
             patch.object(fetch_versions, "fetch_repos", fake_fetch_repos), \
             patch.object(fetch_versions, "fetch_tags", fake_fetch_tags), \
             patch.object(fetch_versions, "datetime", fake_dt), \
             patch.object(fetch_versions, "update_readme"), \
             patch.object(fetch_versions, "update_readme_sha"):
            fetch_versions.main()

    def test_too_new_version_held_back_to_aged_one(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "seen-versions.json").write_text(json.dumps({
                "actions/checkout": {
                    "v4.1.2": {"sha": "sha4", "first_seen": "2026-05-01"},
                    "v5.0.0": {"sha": "sha5", "first_seen": "2026-05-28"},
                }}))
            self._run_main(tmp, {
                "actions/checkout": [("v5", "sha5"), ("v5.0.0", "sha5"),
                                     ("v4.1.2", "sha4")],
            }, date(2026, 5, 29))
            self.assertEqual((tmp / "versions.txt").read_text(),
                             "actions/checkout@v4.1.2\n")
            self.assertEqual((tmp / "versions-sha.txt").read_text(),
                             "actions/checkout@sha4 # v4.1.2\n")
            self.assertNotIn("v5.0.0", (tmp / "versions.txt").read_text())
            self.assertNotIn("v5.0.0", (tmp / "versions-sha.txt").read_text())

    def test_repo_without_semver_omitted(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            (tmp / "seen-versions.json").write_text("{}")
            self._run_main(tmp, {
                "actions/floaty": [("v1", "shaX")],  # only floating major
            }, date(2026, 5, 29))
            self.assertEqual((tmp / "versions.txt").read_text(), "\n")
            self.assertNotIn("actions/floaty",
                             (tmp / "unversioned.txt").read_text())

    def test_moved_tag_poisoned_and_omitted_through_main(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # Aged, trusted entry — but upstream now reports a DIFFERENT sha.
            (tmp / "seen-versions.json").write_text(json.dumps({
                "actions/checkout": {
                    "v1.0.0": {"sha": "OLD", "first_seen": "2026-05-01"},
                }}))
            with patch.object(fetch_versions, "create_tag_moved_issue") as mock_issue:
                self._run_main(tmp, {
                    "actions/checkout": [("v1.0.0", "NEW")],  # immutable tag moved
                }, date(2026, 5, 29))
            # Permanently poisoned in the ledger.
            ledger = json.loads((tmp / "seen-versions.json").read_text())
            self.assertTrue(ledger["actions/checkout"]["v1.0.0"]["bad"])
            # Omitted from output (the only semver tag is poisoned).
            self.assertEqual((tmp / "versions.txt").read_text(), "\n")
            # Exactly one tamper issue opened, for the moved tag.
            mock_issue.assert_called_once_with("actions/checkout", "v1.0.0")

    def test_grandfather_with_brand_new_tag_in_same_run(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)
            # No ledger yet -> grandfather from versions-sha.txt at startup.
            # SHAs must be hex strings to satisfy GRANDFATHER_LINE_RE.
            (tmp / "versions-sha.txt").write_text(
                "actions/checkout@dead0004 # v4.1.2\n")
            self._run_main(tmp, {
                # Upstream also has a brand-new v5.0.0 not yet in the ledger.
                "actions/checkout": [("v5.0.0", "dead0005"), ("v4.1.2", "dead0004")],
            }, date(2026, 5, 29))
            # Grandfathered version offered; brand-new one held back.
            self.assertEqual((tmp / "versions.txt").read_text(),
                             "actions/checkout@v4.1.2\n")
            self.assertEqual((tmp / "versions-sha.txt").read_text(),
                             "actions/checkout@dead0004 # v4.1.2\n")
            ledger = json.loads((tmp / "seen-versions.json").read_text())
            self.assertEqual(ledger["actions/checkout"]["v4.1.2"]["first_seen"],
                             "2000-01-01")
            self.assertEqual(ledger["actions/checkout"]["v5.0.0"]["first_seen"],
                             "2026-05-29")


if __name__ == "__main__":
    unittest.main()
