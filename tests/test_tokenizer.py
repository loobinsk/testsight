from __future__ import annotations

from testsight.config import RunnerConfig
from testsight.resolver import TokenCollector


def test_split_token_handles_camel_case(tmp_path):
    config = RunnerConfig(root=tmp_path)
    collector = TokenCollector(tmp_path, config)
    tokens = collector._split_token("FeatureToggleManager")
    assert {"feature", "toggle", "manager"}.issubset(tokens)


def test_path_tokens_filters_stopwords(tmp_path):
    config = RunnerConfig(root=tmp_path)
    collector = TokenCollector(tmp_path, config)
    path = tmp_path / "src" / "common" / "PaymentCore.py"
    path.parent.mkdir(parents=True)
    path.touch()
    tokens = collector.path_tokens(path)
    assert "payment" in tokens
    assert "common" not in tokens  # filtered by default stopwords


def test_directory_tokens_ignores_filename(tmp_path):
    config = RunnerConfig(root=tmp_path)
    collector = TokenCollector(tmp_path, config)
    path = tmp_path / "src" / "billing" / "adapter" / "fee_engine.py"
    path.parent.mkdir(parents=True)
    path.touch()
    dir_tokens = collector.directory_tokens(path)
    assert "billing" in dir_tokens
    assert "fee" not in dir_tokens


def test_split_token_handles_hyphenated_words(tmp_path):
    config = RunnerConfig(root=tmp_path)
    collector = TokenCollector(tmp_path, config)
    tokens = collector._split_token("payment-engine")
    assert {"payment", "engine"}.issubset(tokens)
