"""Tests for the .argus.yaml config file loader."""

import pytest
from pathlib import Path
from cli.config_file import _parse_yaml, load_repo_config, create_starter_config, RepoConfig


class TestParseYaml:
    def test_empty_string(self):
        config = _parse_yaml("")
        assert config.model is None
        assert config.base_branch is None
        assert config.ignore == []

    def test_comments_and_blank_lines(self):
        config = _parse_yaml("# comment\n\n# another comment\n")
        assert config.model is None

    def test_simple_key_value(self):
        config = _parse_yaml("model: gpt-4\nbase_branch: develop\n")
        assert config.model == "gpt-4"
        assert config.base_branch == "develop"

    def test_quoted_values(self):
        config = _parse_yaml('model: "gpt-4"\nbase_branch: \'main\'\n')
        assert config.model == "gpt-4"
        assert config.base_branch == "main"

    def test_list_items(self):
        yaml_text = 'ignore:\n  - "*.lock"\n  - "dist/"\n  - node_modules/\n'
        config = _parse_yaml(yaml_text)
        assert config.ignore == ["*.lock", "dist/", "node_modules/"]

    def test_full_config(self):
        yaml_text = """
model: llama-3.3-70b-versatile
base_branch: main
review_type: staged
ignore:
  - "*.lock"
  - "package-lock.json"
"""
        config = _parse_yaml(yaml_text)
        assert config.model == "llama-3.3-70b-versatile"
        assert config.base_branch == "main"
        assert config.review_type == "staged"
        assert "*.lock" in config.ignore
        assert "package-lock.json" in config.ignore

    def test_unknown_keys_ignored(self):
        config = _parse_yaml("unknown_key: some_value\nmodel: gpt-4\n")
        assert config.model == "gpt-4"

    def test_review_type(self):
        config = _parse_yaml("review_type: committed\n")
        assert config.review_type == "committed"


class TestLoadRepoConfig:
    def test_no_config_file(self, tmp_path):
        config = load_repo_config(str(tmp_path))
        assert config.model is None
        assert config.ignore == []

    def test_loads_yaml(self, tmp_path):
        (tmp_path / ".argus.yaml").write_text("model: gpt-4\n")
        config = load_repo_config(str(tmp_path))
        assert config.model == "gpt-4"

    def test_loads_yml_extension(self, tmp_path):
        (tmp_path / ".argus.yml").write_text("base_branch: develop\n")
        config = load_repo_config(str(tmp_path))
        assert config.base_branch == "develop"

    def test_yaml_preferred_over_yml(self, tmp_path):
        (tmp_path / ".argus.yaml").write_text("model: gpt-4\n")
        (tmp_path / ".argus.yml").write_text("model: claude\n")
        config = load_repo_config(str(tmp_path))
        assert config.model == "gpt-4"


class TestCreateStarterConfig:
    def test_creates_file(self, tmp_path):
        path = create_starter_config(str(tmp_path))
        assert path.exists()
        assert path.name == ".argus.yaml"
        content = path.read_text()
        assert "ignore:" in content
        assert "*.lock" in content
