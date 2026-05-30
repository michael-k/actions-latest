#!/usr/bin/env python3
"""
Unit tests for fetch_versions.py
"""

import json
import subprocess
import tempfile
import unittest
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


class TestGetLatestVersionTag(unittest.TestCase):
    """Tests for the get_latest_version_tag function."""

    def test_get_latest_version_tag(self):
        """Test getting the latest vINTEGER tag."""
        tags = [
            ("v1", "sha1"),
            ("v2", "sha2"),
            ("v3", "sha3"),
            ("v10", "sha10"),
            ("v2.1.0", "sha2.1.0"),
        ]
        result = fetch_versions.get_latest_version_tag(tags)

        self.assertEqual(result, "v10")

    def test_get_latest_version_tag_no_vinteger(self):
        """Test when repo has no vINTEGER tags."""
        tags = [
            ("v1.0.0", "sha1.0.0"),
            ("v2.0.0", "sha2.0.0"),
            ("release-1", "sha-rel1"),
        ]
        result = fetch_versions.get_latest_version_tag(tags)

        self.assertIsNone(result)

    def test_get_latest_version_tag_empty(self):
        """Test when repo has no tags at all."""
        tags: list[tuple[str, str]] = []
        result = fetch_versions.get_latest_version_tag(tags)

        self.assertIsNone(result)

    def test_version_ordering(self):
        """Test that version ordering is numeric, not lexicographic."""
        tags = [("v9", "sha9"), ("v10", "sha10"), ("v2", "sha2"), ("v1", "sha1")]
        result = fetch_versions.get_latest_version_tag(tags)

        # v10 should be latest, not v9 (which would be latest lexicographically)
        self.assertEqual(result, "v10")


class TestMain(unittest.TestCase):
    """Integration tests for the main function."""

    @patch("fetch_versions.get_latest_version_tag")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_main_integration(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_get_tag,
    ):
        """Test the main function with mocked dependencies."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock fetch_repos to return test data
            mock_fetch_repos.return_value = [
                {"name": "setup-python"},
                {"name": "setup-node"},
                {"name": "no-tags-repo"},
            ]

            # Mock fetch_tags to return tags for each repo
            def fetch_tags_side_effect(org, repo_name):
                if repo_name == "setup-python":
                    return [("v1", "sha1"), ("v2", "sha2"), ("v5", "sha5")]
                elif repo_name == "setup-node":
                    return [
                        ("v1", "sha1"),
                        ("v2", "sha2"),
                        ("v3", "sha3"),
                        ("v4", "sha4"),
                    ]
                else:
                    return []  # no-tags-repo has no tags

            mock_fetch_tags.side_effect = fetch_tags_side_effect

            # Mock get_latest_version_tag to return versions for some repos
            def get_tag_side_effect(tags):
                tag_names = [tag_name for tag_name, _ in tags]
                if "v5" in tag_names:
                    return "v5"
                elif "v4" in tag_names:
                    return "v4"
                else:
                    return None

            mock_get_tag.side_effect = get_tag_side_effect

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(fetch_versions, "ADDITIONAL_ORGS", []):
                    with patch.object(fetch_versions, "ADDITIONAL_REPOS", []):
                        fetch_versions.main()

            # Verify the versions file was written correctly
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 2)
            self.assertIn("actions/setup-node@v4", lines)
            self.assertIn("actions/setup-python@v5", lines)

            # Verify alphabetical ordering (setup-node before setup-python)
            self.assertEqual(lines[0], "actions/setup-node@v4")
            self.assertEqual(lines[1], "actions/setup-python@v5")

            # Verify unversioned repos were saved
            unversioned_file = Path(tmpdir) / "unversioned.txt"
            unversioned_content = unversioned_file.read_text()
            self.assertIn("actions/no-tags-repo", unversioned_content)

    @patch("fetch_versions.get_latest_version_tag")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_main_skips_cached_unversioned(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_get_tag,
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
            mock_get_tag.return_value = "v5"

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

    @patch("fetch_versions.get_latest_semver_tag")
    @patch("fetch_versions.get_latest_version_tag")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_semver_fallback_no_vinteger(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_get_tag,
        mock_get_semver,
    ):
        """Test semver fallback when repo has no vINTEGER tags."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock fetch_repos to return a repo with only semver tags
            mock_fetch_repos.return_value = [{"name": "setup-ruby"}]

            # Mock fetch_tags to return semver tags only (no vINTEGER)
            mock_fetch_tags.return_value = [
                ("v1.4.0", "sha1"),
                ("v1.5.0", "sha2"),
                ("v1.5.1", "sha3"),
            ]

            # No vINTEGER tag, but latest semver available
            mock_get_tag.return_value = None
            mock_get_semver.return_value = ("v1.5.1", "sha3")

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(fetch_versions, "ADDITIONAL_ORGS", []):
                    with patch.object(fetch_versions, "ADDITIONAL_REPOS", []):
                        fetch_versions.main()

            # Verify the semver tag was used as fallback
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

    @patch("fetch_versions.get_latest_semver_tag")
    @patch("fetch_versions.get_latest_version_tag")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_vinteger_takes_precedence(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_get_tag,
        mock_get_semver,
    ):
        """Test that vINTEGER tag is preferred over semver when both exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
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

            # Both types available
            mock_get_tag.return_value = "v3"
            mock_get_semver.return_value = ("v3.5.2", "sha3")

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(fetch_versions, "ADDITIONAL_ORGS", []):
                    with patch.object(fetch_versions, "ADDITIONAL_REPOS", []):
                        fetch_versions.main()

            # Verify vINTEGER tag was used (not semver)
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 1)
            self.assertEqual(lines[0], "actions/setup-node@v3")

    @patch("fetch_versions.get_latest_semver_tag")
    @patch("fetch_versions.get_latest_version_tag")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_no_version_tags_marks_unversioned(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_get_tag,
        mock_get_semver,
    ):
        """Test that repos with no version tags are still marked as unversioned."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock fetch_repos
            mock_fetch_repos.return_value = [{"name": "no-tags-repo"}]

            # No tags at all
            mock_fetch_tags.return_value = []
            mock_get_tag.return_value = None
            mock_get_semver.return_value = None

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

    @patch("fetch_versions.get_latest_semver_tag")
    @patch("fetch_versions.get_latest_version_tag")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_skip_repos_filters_out_specified_repos(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_get_tag,
        mock_get_semver,
    ):
        """Test that repos in SKIP_REPOS are not processed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock fetch_repos to return multiple repos
            mock_fetch_repos.return_value = [
                {"name": "setup-python"},
                {"name": "setup-node"},
                {"name": "skip-me"},
                {"name": "also-skip"},
            ]

            # Mock fetch_tags and version tags
            mock_fetch_tags.return_value = [("v1", "sha1"), ("v5", "sha5")]
            mock_get_tag.return_value = "v5"
            mock_get_semver.return_value = None

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(fetch_versions, "ADDITIONAL_ORGS", []):
                    with patch.object(fetch_versions, "ADDITIONAL_REPOS", []):
                        with patch.object(
                            fetch_versions, "SKIP_REPOS", ["skip-me", "also-skip"]
                        ):
                            fetch_versions.main()

            # Verify only non-skipped repos are in versions.txt
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 2)
            self.assertIn("actions/setup-python@v5", lines)
            self.assertIn("actions/setup-node@v5", lines)
            self.assertNotIn("actions/skip-me", content)
            self.assertNotIn("actions/also-skip", content)

            # Verify skipped repos were not cached as unversioned
            unversioned_file = Path(tmpdir) / "unversioned.txt"
            unversioned_content = unversioned_file.read_text()
            self.assertNotIn("actions/skip-me", unversioned_content)
            self.assertNotIn("actions/also-skip", unversioned_content)


class TestAdditionalRepos(unittest.TestCase):
    """Tests for additional repos functionality."""

    @patch("fetch_versions.get_latest_semver_tag")
    @patch("fetch_versions.get_latest_version_tag")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_main_with_additional_repos(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_get_tag,
        mock_get_semver,
    ):
        """Test main function with additional repos."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Mock fetch_repos for main org
            mock_fetch_repos.return_value = [{"name": "setup-python"}]

            # Mock fetch_tags responses
            def fetch_tags_side_effect(org, repo_name):
                if org == "actions" and repo_name == "setup-python":
                    return [("v1", "sha1"), ("v5", "sha5")]
                elif org == "other" and repo_name == "some-action":
                    return [("v2", "sha2"), ("v3", "sha3")]
                return []

            mock_fetch_tags.side_effect = fetch_tags_side_effect

            # Mock get_latest_version_tag
            def get_tag_side_effect(tags):
                tag_names = [tag for tag, sha in tags]
                if "v5" in tag_names:
                    return "v5"
                elif "v3" in tag_names:
                    return "v3"
                return None

            mock_get_tag.side_effect = get_tag_side_effect
            mock_get_semver.return_value = None

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(
                    fetch_versions, "ADDITIONAL_REPOS", ["other/some-action"]
                ):
                    with patch.object(fetch_versions, "ADDITIONAL_ORGS", []):
                        fetch_versions.main()

            # Verify the versions file contains both repos
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")

            self.assertEqual(len(lines), 2)
            self.assertIn("actions/setup-python@v5", lines)
            self.assertIn("other/some-action@v3", lines)


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

    @patch("fetch_versions.get_latest_semver_tag")
    @patch("fetch_versions.get_latest_version_tag")
    @patch("fetch_versions.fetch_tags")
    @patch("fetch_versions.fetch_repos")
    def test_main_with_additional_orgs(
        self,
        mock_fetch_repos,
        mock_fetch_tags,
        mock_get_tag,
        mock_get_semver,
    ):
        """Test main function with additional orgs."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # No cached unversioned repos

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
                    return [
                        ("v1", "sha1"),
                        ("v2", "sha2"),
                        ("v5", "sha5"),
                        ("v5.0.0", "sha5"),
                    ]
                elif org == "aws-actions" and repo_name == "configure-aws-credentials":
                    return [("v1", "sha1"), ("v4", "sha4"), ("v4.0.0", "sha4")]
                return []

            mock_fetch_tags.side_effect = fetch_tags_side_effect

            # Mock get_latest_version_tag
            def get_tag_side_effect(tags):
                tag_names = [tag_name for tag_name, _ in tags]
                if "v5" in tag_names:
                    return "v5"
                elif "v4" in tag_names:
                    return "v4"
                return None

            mock_get_tag.side_effect = get_tag_side_effect

            # Mock get_latest_semver_tag to provide semver info
            def get_semver_side_effect(tags):
                tag_names = [tag_name for tag_name, _ in tags]
                if "v5.0.0" in tag_names:
                    return ("v5.0.0", "sha5")
                elif "v4.0.0" in tag_names:
                    return ("v4.0.0", "sha4")
                return None

            mock_get_semver.side_effect = get_semver_side_effect

            with patch.object(fetch_versions, "SCRIPT_DIR", Path(tmpdir)):
                with patch.object(fetch_versions, "ADDITIONAL_ORGS", ["aws-actions"]):
                    with patch.object(fetch_versions, "ADDITIONAL_REPOS", []):
                        fetch_versions.main()

            # Verify the main versions file contains only actions org repos (not from ADDITIONAL_ORGS)
            versions_file = Path(tmpdir) / "versions.txt"
            content = versions_file.read_text()
            lines = content.strip().split("\n")
            self.assertEqual(len(lines), 1)
            self.assertIn("actions/setup-python@v5", lines)
            self.assertNotIn("aws-actions/configure-aws-credentials", content)

            # Verify the org-specific versions file contains only aws-actions repos
            aws_versions_file = Path(tmpdir) / "aws-actions-versions.txt"
            aws_content = aws_versions_file.read_text()
            aws_lines = aws_content.strip().split("\n")
            self.assertEqual(len(aws_lines), 1)
            self.assertEqual(aws_lines[0], "aws-actions/configure-aws-credentials@v4")


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
        mock_base_url.return_value = "https://michael-k.github.io/actions-latest/"

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
                "https://michael-k.github.io/actions-latest/versions.txt",
            )
            self.assertEqual(
                index["bundles"]["default"]["versions_sha_url"],
                "https://michael-k.github.io/actions-latest/versions-sha.txt",
            )

            # Verify org URLs
            self.assertEqual(
                index["orgs"]["aws-actions"]["versions_url"],
                "https://michael-k.github.io/actions-latest/aws-actions-versions.txt",
            )
            self.assertEqual(
                index["orgs"]["docker"]["versions_sha_url"],
                "https://michael-k.github.io/actions-latest/docker-versions-sha.txt",
            )

    @patch("fetch_versions.subprocess.run")
    def test_get_base_url_from_git(self, mock_run):
        """Test that base URL is derived from git config."""
        mock_run.return_value = MagicMock(
            stdout="https://github.com/michael-k/actions-latest.git",
            returncode=0,
        )

        result = fetch_versions.get_base_url()

        self.assertEqual(result, "https://michael-k.github.io/actions-latest/")

    @patch("fetch_versions.subprocess.run")
    def test_get_base_url_fallback(self, mock_run):
        """Test that base URL falls back to default when git config fails."""
        mock_run.return_value = MagicMock(stdout="", returncode=1)

        result = fetch_versions.get_base_url()

        self.assertEqual(result, "https://michael-k.github.io/actions-latest/")


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


if __name__ == "__main__":
    unittest.main()
