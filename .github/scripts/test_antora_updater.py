#!/usr/bin/env python

import sys
import unittest
import types
import logging
import urllib.request
from unittest.mock import patch, call, MagicMock
from ruamel.yaml import YAML

def initialize_test_environment() -> None:
    if "antora_utils" not in sys.modules:
        class DynamicMockModule(types.ModuleType):
            def __getattr__(self, name):
                if name == "setup_logger":
                    return lambda name: logging.getLogger(name)
                return MagicMock()

        dummy_utils = DynamicMockModule("antora_utils")
        sys.modules["antora_utils"] = dummy_utils

    global antora
    with patch("urllib.request.urlretrieve") as mock_init_urlretrieve:
        import antora_updater as antora

initialize_test_environment()

class DynamicFileSimulator:
    def __init__(self, initial_content: str):
        self.content = initial_content
        self.history = []

    def open_stream(self, file_path: str, mode: str):
        return VirtualFileContext(self, mode)

class VirtualFileContext:
    def __init__(self, factory: DynamicFileSimulator, mode: str):
        self.factory = factory
        self.mode = mode
        self.read_done = False
        self.local_buffer = []

    def read(self, *args, **kwargs) -> str:
        if ("r" in self.mode or "+" in self.mode) and not self.read_done:
            self.read_done = True
            return self.factory.content
        return ""

    def write(self, data) -> int:
        text_chunk = data.decode("utf-8") if isinstance(data, bytes) else data
        self.local_buffer.append(text_chunk)
        return len(data)

    def seek(self, position: int, *args, **kwargs) -> None:
        if position == 0:
            self.local_buffer = []

    def truncate(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if ("w" in self.mode or "+" in self.mode) and self.local_buffer:
            completed_doc = "".join(self.local_buffer)
            self.factory.content = completed_doc
            self.factory.history.append(completed_doc)


class TestAntoraUpdater(unittest.TestCase):

    def setUp(self) -> None:
        self.yaml: YAML = YAML()
        self.yaml.preserve_quotes = True

    def get_main_template(self) -> str:
        return """name: hazelcast-management-center
title: Hazelcast Management Center
version: 'main'
display_version: 'main'
asciidoc:
  attributes:
    page-latest-supported-hazelcast: '5.8-snapshot'
    experimental: true
nav:
  - modules/ROOT/nav.adoc
"""

    def get_release_template(self) -> str:
        return """name: hazelcast-management-center
title: Hazelcast Management Center
version: '5.11'
display_version: '5.11'
asciidoc:
  attributes:
    page-latest-supported-hazelcast: '5.7'
    experimental: true
nav:
  - modules/ROOT/nav.adoc
"""

    def assert_untouched_properties(self, data: dict) -> None:
        self.assertEqual(data["name"], "hazelcast-management-center")
        self.assertTrue(data["asciidoc"]["attributes"]["experimental"])

    def test_update_is_rel_major_minor_true(self) -> None:
        simulator = DynamicFileSimulator(self.get_main_template())

        with patch("builtins.open", side_effect=simulator.open_stream) as mock_open, \
             patch("antora_utils.checkout_branch", return_value="update_mock_branch_123") as mock_checkout, \
             patch("antora_utils.commit_changes") as mock_commit, \
             patch("antora_utils.create_github_pr") as mock_pr:

            antora.update(
                release_ver="5.8.0",
                rel_major_minor="5.8",
                master_version="5.9.0-SNAPSHOT",
                master_major_minor="5.9",
                mc_major_minor="5.11",
                is_latest_stable_release="false",
                is_rel_major_minor="true",
                is_patch_release="false"
            )

            self.assertEqual(len(simulator.history), 2)
            mock_checkout.assert_any_call("antora", "main")
            mock_checkout.assert_any_call("antora", "v/5.11")

            main_data = self.yaml.load(simulator.history[0])
            release_data = self.yaml.load(simulator.history[1])

            self.assertEqual(main_data["asciidoc"]["attributes"]["page-latest-supported-hazelcast"], "5.9-snapshot")
            self.assert_untouched_properties(main_data)

            self.assertEqual(release_data["asciidoc"]["attributes"]["page-latest-supported-hazelcast"], "5.8")
            self.assert_untouched_properties(release_data)
            mock_commit.assert_any_call("main", "5.9.0-SNAPSHOT", ["docs/antora.yml"], "update_mock_branch_123")
            mock_commit.assert_any_call("v/5.11", "5.8.0", ["docs/antora.yml"], "update_mock_branch_123")
            mock_pr.assert_any_call("main", "update_mock_branch_123", "5.9.0-SNAPSHOT")
            mock_pr.assert_any_call("v/5.11", "update_mock_branch_123", "5.8.0")

    def test_update_patch_and_latest_stable_with_changes(self) -> None:
        simulator = DynamicFileSimulator(self.get_release_template())

        with patch("builtins.open", side_effect=simulator.open_stream) as mock_open, \
             patch("antora_utils.checkout_branch", return_value="update_mock_branch_123") as mock_checkout, \
             patch("antora_utils.commit_changes") as mock_commit, \
             patch("antora_utils.create_github_pr") as mock_pr:

            antora.update(
                release_ver="5.8.1",
                rel_major_minor="5.8",
                master_version="5.8.1-SNAPSHOT",
                master_major_minor="5.8",
                mc_major_minor="5.11",
                is_latest_stable_release="true",
                is_rel_major_minor="false",
                is_patch_release="true"
            )

            self.assertEqual(len(simulator.history), 1)
            mock_checkout.assert_called_once_with("antora", "v/5.11")

            release_data = self.yaml.load(simulator.history[0])
            self.assertEqual(release_data["asciidoc"]["attributes"]["page-latest-supported-hazelcast"], "5.8")
            self.assert_untouched_properties(release_data)

            mock_commit.assert_called_once_with("v/5.11", "5.8.1", ["docs/antora.yml"], "update_mock_branch_123")
            mock_pr.assert_called_once_with("v/5.11", "update_mock_branch_123", "5.8.1")

    def test_update_patch_and_latest_stable_already_matching_skips(self) -> None:
        simulator = DynamicFileSimulator(self.get_release_template())

        with patch("builtins.open", side_effect=simulator.open_stream) as mock_open, \
             patch("antora_utils.checkout_branch", return_value="update_mock_branch_123") as mock_checkout, \
             patch("antora_utils.commit_changes") as mock_commit, \
             patch("antora_utils.create_github_pr") as mock_pr, \
             patch("antora_updater.logger.warning") as mock_warn:

            antora.update(
                release_ver="5.7.1",
                rel_major_minor="5.7",
                master_version="5.7.1-SNAPSHOT",
                master_major_minor="5.7",
                mc_major_minor="5.11",
                is_latest_stable_release="true",
                is_rel_major_minor="false",
                is_patch_release="true"
            )

            self.assertEqual(len(simulator.history), 0)
            mock_checkout.assert_called_once_with("antora", "v/5.11")
            mock_warn.assert_called_once_with("Skipping update - current 'page-latest-supported-hazelcast' value '5.7' already matches '5.7'")
            mock_commit.assert_not_called()
            mock_pr.assert_not_called()

    def test_update_skip_scenario_beta(self) -> None:
        simulator = DynamicFileSimulator(self.get_release_template())

        with patch("builtins.open", side_effect=simulator.open_stream), \
             patch("antora_utils.checkout_branch") as mock_checkout, \
             patch("antora_updater.logger.info") as mock_logger_info:

            antora.update(
                release_ver="5.8.0-BETA1",
                rel_major_minor="5.8",
                master_version="5.9.0-SNAPSHOT",
                master_major_minor="5.9",
                mc_major_minor="5.11",
                is_latest_stable_release="false",
                is_rel_major_minor="false",
                is_patch_release="false"
            )

            self.assertEqual(len(simulator.history), 0)
            mock_checkout.assert_not_called()
            mock_logger_info.assert_called_once_with("Skip 'antora.yml' updates for BETA or PATCH (non latest) release")

    def test_update_skip_scenario_non_latest_patch(self) -> None:
        simulator = DynamicFileSimulator(self.get_release_template())

        with patch("builtins.open", side_effect=simulator.open_stream), \
             patch("antora_utils.checkout_branch") as mock_checkout, \
             patch("antora_updater.logger.info") as mock_logger_info:

            antora.update(
                release_ver="5.6.4",
                rel_major_minor="5.6",
                master_version="5.9.0-SNAPSHOT",
                master_major_minor="5.9",
                mc_major_minor="5.11",
                is_latest_stable_release="false",
                is_rel_major_minor="false",
                is_patch_release="true"
            )

            self.assertEqual(len(simulator.history), 0)
            mock_checkout.assert_not_called()
            mock_logger_info.assert_called_once_with("Skip 'antora.yml' updates for BETA or PATCH (non latest) release")
    @patch("antora_utils.merge_github_pr")
    def test_merge_pull_requests_major_minor(self, mock_merge) -> None:
        antora.merge_pull_requests(
            is_rel_major_minor="true",
            is_patch_release="false",
            is_latest_stable_release="false",
            release_version="5.8.0",
            master_version="5.9.0-SNAPSHOT",
            mc_major_minor="5.11"
        )

        mock_merge.assert_any_call("main", "5.9.0-SNAPSHOT")
        mock_merge.assert_any_call("v/5.11", "5.8.0", fail_on_missing=True)

    @patch("antora_utils.merge_github_pr")
    def test_merge_pull_requests_patch_and_stable(self, mock_merge) -> None:
        antora.merge_pull_requests(
            is_rel_major_minor="false",
            is_patch_release="true",
            is_latest_stable_release="true",
            release_version="5.8.1",
            master_version="5.8.1-SNAPSHOT",
            mc_major_minor="5.11"
        )

        mock_merge.assert_called_once_with("v/5.11", "5.8.1", fail_on_missing=False)

    @patch("antora_utils.merge_github_pr")
    def test_merge_pull_requests_skip(self, mock_merge) -> None:
        with patch("antora_updater.logger.info") as mock_info:
            antora.merge_pull_requests(
                is_rel_major_minor="false",
                is_patch_release="true",
                is_latest_stable_release="false",
                release_version="5.6.4",
                master_version="5.9.0-SNAPSHOT",
                mc_major_minor="5.11"
            )
            mock_merge.assert_not_called()
            mock_info.assert_called_once_with("Skip 'antora.yml' updates for BETA or PATCH (non latest) release")

    def test_update_patch_and_latest_stable_does_not_skip_on_snapshot_variants(self) -> None:
        simulator = DynamicFileSimulator(self.get_release_template())
        simulator.content = simulator.content.replace("'5.7'", "'5.8-SNAPSHOT'")

        with patch("builtins.open", side_effect=simulator.open_stream), \
             patch("antora_utils.checkout_branch", return_value="update_mock_branch_123") as mock_checkout, \
             patch("antora_utils.commit_changes") as mock_commit, \
             patch("antora_utils.create_github_pr") as mock_pr, \
             patch("antora_updater.logger.warning") as mock_warn:

            antora.update(
                release_ver="5.8.1",
                rel_major_minor="5.8",
                master_version="5.8.1-SNAPSHOT",
                master_major_minor="5.8",
                mc_major_minor="5.11",
                is_latest_stable_release="true",
                is_rel_major_minor="false",
                is_patch_release="true"
            )

            self.assertEqual(len(simulator.history), 1)
            mock_checkout.assert_called_once_with("antora", "v/5.11")
            mock_warn.assert_not_called()
            mock_commit.assert_called_once()
            mock_pr.assert_called_once()

            release_data = self.yaml.load(simulator.history[0])
            self.assertEqual(release_data["asciidoc"]["attributes"]["page-latest-supported-hazelcast"], "5.8")

if __name__ == "__main__":
    unittest.main(testRunner=unittest.TextTestRunner(verbosity=2))
