from __future__ import annotations

from testsight.config import RunnerConfig
from testsight.indexer import ModuleIndexer, analyze_module, build_module_data


def test_indexer_handles_src_layout(tmp_path):
    (tmp_path / "src" / "app").mkdir(parents=True)
    (tmp_path / "src" / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "src" / "app" / "service.py").write_text(
        "def ping():\n    return 1\n", encoding="utf-8"
    )

    config = RunnerConfig(root=tmp_path)
    index = ModuleIndexer(config).build()

    assert "app.service" in index.modules
    assert index.modules["app.service"].path.name == "service.py"


def test_indexer_skips_excluded_dirs(tmp_path):
    (tmp_path / ".venv" / "pkg").mkdir(parents=True)
    (tmp_path / ".venv" / "pkg" / "mod.py").write_text(
        """VALUE = 1""", encoding="utf-8"
    )

    config = RunnerConfig(root=tmp_path)
    index = ModuleIndexer(config).build()

    assert not index.modules


def test_analyze_module_exports_and_imports(tmp_path):
    module = tmp_path / "core.py"
    module.write_text(
        """
import math
from math import sqrt as root

CONSTANT = 1


def use(value):
    return root(value) + math.ceil(value)
""".strip()
        + "\n",
        encoding="utf-8",
    )

    config = RunnerConfig(root=tmp_path)
    indexer = ModuleIndexer(config)
    module_name = indexer.derive_module_name(module)
    info = indexer.build().modules[module_name]

    data = analyze_module(info)
    assert {"CONSTANT", "use", "root", "math"}.issubset(data.exports)
    assert "math" in data.imports

    module_data, reverse = build_module_data(ModuleIndexer(config).build())
    assert module_name in module_data
    assert module_name in reverse.get("math", {}).get(None, set())
