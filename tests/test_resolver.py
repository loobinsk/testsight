from __future__ import annotations

from pathlib import Path

from testsight.config import RunnerConfig, TokenConfig
from testsight.indexer import ModuleIndexer
from testsight.resolver import ImpactResolver, prepare_analysis


def make_basic_layout(root: Path) -> None:
    (root / "tests").mkdir(parents=True)
    (root / "feature.py").write_text(
        """
VALUE = 1


def compute(x):
    return x + VALUE
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (root / "tests" / "test_feature.py").write_text(
        """
from feature import compute


def test_compute():
    assert compute(4) == 5
""".strip()
        + "\n",
        encoding="utf-8",
    )


def test_resolver_detects_direct_dependency(tmp_path):
    make_basic_layout(tmp_path)
    config = RunnerConfig(root=tmp_path)
    index = ModuleIndexer(config).build()
    analysis = prepare_analysis(index)
    resolver = ImpactResolver(config, index, analysis)
    changed = [tmp_path / "feature.py"]
    tests = resolver.resolve(changed)
    assert tests == [tmp_path / "tests" / "test_feature.py"]


def test_resolver_filters_by_symbol(tmp_path):
    make_basic_layout(tmp_path)
    (tmp_path / "consumer.py").write_text(
        """
from feature import compute


def adapter(val):
    return compute(val)
""".strip()
        + "\n",
        encoding="utf-8",
    )
    (tmp_path / "tests" / "test_consumer.py").write_text(
        """
from consumer import adapter


def test_adapter():
    assert adapter(2) == 3
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config = RunnerConfig(root=tmp_path)
    index = ModuleIndexer(config).build()
    analysis = prepare_analysis(index)
    resolver = ImpactResolver(config, index, analysis)

    changed = [tmp_path / "consumer.py"]
    tests = resolver.resolve(changed)
    assert tests == [tmp_path / "tests" / "test_consumer.py"]


def test_resolver_uses_fallback_matching(tmp_path):
    (tmp_path / "src" / "billing").mkdir(parents=True)
    (tmp_path / "src" / "billing" / "tax.py").write_text(
        "RATE = 0.2\n", encoding="utf-8"
    )
    (tmp_path / "tests" / "billing").mkdir(parents=True)
    (tmp_path / "tests" / "billing" / "test_tax.py").write_text(
        "from src.billing import tax\n", encoding="utf-8"
    )

    config = RunnerConfig(root=tmp_path).with_overrides(
        tokens=TokenConfig(fallback_score=3)
    )
    index = ModuleIndexer(config).build()
    analysis = prepare_analysis(index)
    resolver = ImpactResolver(config, index, analysis)

    changed = [tmp_path / "src" / "billing" / "tax.py"]
    tests = resolver.resolve(changed)
    assert tests == [tmp_path / "tests" / "billing" / "test_tax.py"]


def test_resolver_returns_sorted_paths(tmp_path):
    make_basic_layout(tmp_path)
    (tmp_path / "tests" / "zeta_test.py").write_text(
        "def test_dummy():\n    assert True\n", encoding="utf-8"
    )
    config = RunnerConfig(root=tmp_path)
    index = ModuleIndexer(config).build()
    analysis = prepare_analysis(index)
    resolver = ImpactResolver(config, index, analysis)

    changed = [tmp_path / "tests" / "zeta_test.py", tmp_path / "feature.py"]
    tests = resolver.resolve(changed)
    assert tests == sorted(tests)
