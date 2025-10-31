# Testsight — 🎯 smarter, faster test runs

Testsight keeps your CI and local loops fast. It translates Git diffs into a focused pytest run by analysing module dependencies, mapping them back to test modules and running only what matters.

```
🚀 Git diff → 🧠 Import graph → 🎯 Impacted tests → ✅ Focused pytest run
```

## ✨ Highlights
- 🧭 **Static dependency graph** — symbol-aware BFS avoids re-running the entire suite when a hub module changes.
- 🪄 **Token-based fallback** — clever path tokenisation catches dynamic imports and naming conventions.
- 🧱 **Strong configurability** — CLI flags, TOML files and env vars let you personalise diff strategy, test naming, runner command and more.
- 🧪 **20 pytest scenarios** — the repository ships with realistic tests that stage/commit files and exercise the CLI end-to-end.
- 🧰 **No hard-coded assumptions** — no implicit reliance on Poetry, particular layouts or CI flavours.

## 🚀 Quick start
```bash
poetry install        # or: python3.10 -m venv .venv && .venv/bin/pip install -e .
poetry run testsight  # inspect staged changes and execute impacted tests
```

### CLI sampler
```bash
# Inspect without executing
poetry run testsight --dry-run

# CI-friendly JSON output
poetry run testsight --json

# Analyse a commit range
poetry run testsight --diff-mode range --base origin/main --head HEAD

# Run via your favourite toolchain
poetry run testsight --test-command "tox -e py310 --"
```

## ⚙️ Configuration
Testsight looks for `testsight.toml`, `.testsightrc` or `[tool.testsight]` within `pyproject.toml`. Every option has a CLI/env override (`TESTSIGHT_*`).

```toml
[testsight]
root = "."
test-command = "pytest -q --maxfail=1"

[testsight.diff]
mode = "staged"          # staged | unstaged | range | custom
include-untracked = true

[testsight.naming]
directory-markers = ["tests", "integration"]
filename-prefixes = ["test_"]
filename-suffixes = ["_test.py"]

[testsight.tokens]
minimum-length = 3
fallback-score = 8
stopwords = ["common", "shared"]
```

## 🧠 Architecture
- `testsight.config` — configuration loaders and merge logic.
- `testsight.indexer` — module discovery and AST analysis.
- `testsight.resolver` — dependency graph walk and token fallback.
- `testsight.runner` — Git integration + command orchestration.
- `testsight.cli` — user-facing entry point.

Async IO isn’t used on purpose: building the graph is CPU-bound and runs once per invocation, so asyncio would add complexity without measurable wins.

## 🧪 Tests & demos
Twenty pytest cases live under `tests/`; they create temporary repos, run `git add/commit`, call the CLI and verify outcomes. Perfect for documentation and regression coverage.

```bash
python3.10 -m venv .venv
source .venv/bin/activate
pip install -e .
PYTHONPATH=src pytest -q
```

## 📚 Handy commands
- `poetry run testsight --help` — full CLI reference.
- `poetry run testsight path/to/file.py` — manually provide changed files.
- `poetry run testsight --config ci/testsight.toml --json` — typical CI usage.

## 🤝 Contributing
1. Fork the Testsight repository.
2. Create a `feature/my-idea` branch.
3. Add tests (`poetry run pytest`).
4. Open a PR and describe how it speeds up feedback.

Ideas, bug reports and feature requests are welcome. Let’s make targeted testing effortless! 🚀
