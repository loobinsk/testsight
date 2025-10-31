"""Configuration utilities for Testsight."""

from __future__ import annotations

import os
import shlex
from dataclasses import dataclass, field, replace
from enum import Enum
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping, Sequence

try:  # pragma: no cover - Python 3.10 compatibility shim
    import tomllib  # type: ignore[attr-defined]
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None  # type: ignore[assignment]


DEFAULT_EXCLUDE_DIRS: tuple[str, ...] = (
    ".git",
    ".hg",
    ".mypy_cache",
    ".pytest_cache",
    ".tox",
    ".venv",
    "__pycache__",
    "build",
    "dist",
    "node_modules",
    "venv",
)

DEFAULT_GENERIC_TOKENS: tuple[str, ...] = (
    "api",
    "apis",
    "base",
    "build",
    "common",
    "core",
    "data",
    "init",
    "lib",
    "model",
    "models",
    "query",
    "queries",
    "service",
    "services",
    "src",
    "test",
    "tests",
    "util",
    "utils",
)

DEFAULT_TEST_COMMAND = ("pytest", "-q", "--maxfail=1")


class DiffSource(str, Enum):
    """Git diff source used to discover changed files."""

    STAGED = "staged"
    UNSTAGED = "unstaged"
    RANGE = "range"
    CUSTOM = "custom"


@dataclass(frozen=True)
class DiffConfig:
    """Options describing how to obtain the list of changed files."""

    mode: DiffSource = DiffSource.STAGED
    base: str | None = None
    head: str | None = None
    custom_args: tuple[str, ...] = ()
    diff_filter: str = "ACMR"
    include_untracked: bool = False


@dataclass(frozen=True)
class TestNamingRules:
    """Rules for identifying test modules."""

    directory_markers: tuple[str, ...] = ("tests",)
    filename_prefixes: tuple[str, ...] = ("test_",)
    filename_suffixes: tuple[str, ...] = ("_test.py",)

    def is_test_file(self, path: Path, root: Path, suffixes: Sequence[str]) -> bool:
        relative = path.relative_to(root)
        parts = relative.parts
        name = path.name

        in_marked_directory = any(part in self.directory_markers for part in parts[:-1])
        has_prefix = any(name.startswith(prefix) for prefix in self.filename_prefixes)
        has_suffix = any(name.endswith(suffix) for suffix in self.filename_suffixes)
        extension_ok = any(name.endswith(suffix) for suffix in suffixes)

        if in_marked_directory:
            return (has_prefix or has_suffix) and extension_ok
        return has_prefix and extension_ok or has_suffix


@dataclass(frozen=True)
class TokenConfig:
    """Settings controlling token extraction."""

    minimum_length: int = 3
    fallback_score: int = 12
    stopwords: tuple[str, ...] = DEFAULT_GENERIC_TOKENS


@dataclass(frozen=True)
class RunnerConfig:
    """Top-level configuration consumed by :class:`TestsightRunner`."""

    root: Path
    diff: DiffConfig = field(default_factory=DiffConfig)
    test_command: tuple[str, ...] = DEFAULT_TEST_COMMAND
    python_suffixes: tuple[str, ...] = (".py",)
    source_roots: tuple[str, ...] = ("src",)
    exclude_dirs: tuple[str, ...] = DEFAULT_EXCLUDE_DIRS
    naming: TestNamingRules = field(default_factory=TestNamingRules)
    tokens: TokenConfig = field(default_factory=TokenConfig)
    dry_run: bool = False
    quiet: bool = False
    print_command: bool = True
    env: Mapping[str, str] | None = None

    def with_overrides(self, **updates: object) -> "RunnerConfig":
        return replace(self, **updates)


def parse_command(command: str | Sequence[str] | None) -> tuple[str, ...]:
    if command is None:
        return DEFAULT_TEST_COMMAND
    if isinstance(command, str):
        tokens = shlex.split(command)
    else:
        tokens = list(command)
    if not tokens:
        raise ValueError("Test command must not be empty")
    return tuple(tokens)


def find_repo_root(start: Path | None = None) -> Path:
    """Locate the nearest directory containing a `.git` folder."""

    start = start or Path.cwd()
    current = start.resolve()
    for path in [current, *current.parents]:
        if (path / ".git").exists():
            return path
    return current


def _load_toml(path: Path) -> Mapping[str, object]:
    if tomllib is None:
        raise RuntimeError(
            "Reading configuration files requires tomllib (Python 3.11+) or tomli as a dependency."
        )
    with path.open("rb") as handle:
        return tomllib.load(handle)


def load_config_from_mapping(
    root: Path,
    data: Mapping[str, object],
    base: RunnerConfig | None = None,
) -> RunnerConfig:
    """Create a :class:`RunnerConfig` from a raw mapping (e.g. parsed TOML)."""

    base = base or RunnerConfig(root=root)

    def get_sequence_from(
        mapping: Mapping[str, object],
        key: str,
        default: Iterable[str],
    ) -> tuple[str, ...]:
        value = mapping.get(key, default)
        if isinstance(value, str):
            return tuple(shlex.split(value))
        if isinstance(value, Iterable):
            return tuple(str(item) for item in value)
        raise TypeError(f"Configuration key '{key}' must be a sequence or string.")

    overrides: MutableMapping[str, object] = {}

    if "test-command" in data:
        overrides["test_command"] = parse_command(data["test-command"])

    if "python-suffixes" in data:
        overrides["python_suffixes"] = tuple(
            str(s) for s in get_sequence_from(data, "python-suffixes", (".py",))
        )
    if "source-roots" in data:
        overrides["source_roots"] = tuple(
            str(s) for s in get_sequence_from(data, "source-roots", base.source_roots)
        )

    if "exclude-dirs" in data:
        overrides["exclude_dirs"] = tuple(
            str(s) for s in get_sequence_from(data, "exclude-dirs", base.exclude_dirs)
        )

    if "dry-run" in data:
        overrides["dry_run"] = bool(data["dry-run"])

    if "quiet" in data:
        overrides["quiet"] = bool(data["quiet"])

    if "print-command" in data:
        overrides["print_command"] = bool(data["print-command"])

    if "env" in data:
        env_section = data["env"]
        if not isinstance(env_section, Mapping):
            raise TypeError("Configuration key 'env' must be a table/dict")
        overrides["env"] = {str(k): str(v) for k, v in env_section.items()}

    naming_section = data.get("naming")
    if isinstance(naming_section, Mapping):
        overrides["naming"] = TestNamingRules(
            directory_markers=tuple(
                str(item)
                for item in get_sequence_from(
                    naming_section,
                    "directory-markers",
                    TestNamingRules().directory_markers,
                )
            ),
            filename_prefixes=tuple(
                str(item)
                for item in get_sequence_from(
                    naming_section,
                    "filename-prefixes",
                    TestNamingRules().filename_prefixes,
                )
            ),
            filename_suffixes=tuple(
                str(item)
                for item in get_sequence_from(
                    naming_section,
                    "filename-suffixes",
                    TestNamingRules().filename_suffixes,
                )
            ),
        )

    tokens_section = data.get("tokens")
    if isinstance(tokens_section, Mapping):
        overrides["tokens"] = TokenConfig(
            minimum_length=int(
                tokens_section.get("minimum-length", base.tokens.minimum_length)
            ),
            fallback_score=int(
                tokens_section.get("fallback-score", base.tokens.fallback_score)
            ),
            stopwords=tuple(
                str(item)
                for item in get_sequence_from(
                    tokens_section, "stopwords", base.tokens.stopwords
                )
            ),
        )

    diff_section = data.get("diff")
    if isinstance(diff_section, Mapping):
        mode_value = diff_section.get("mode", base.diff.mode.value)
        diff_mode = DiffSource(mode_value) if mode_value is not None else base.diff.mode
        diff_overrides: dict[str, object] = {"mode": diff_mode}

        if "base" in diff_section:
            diff_overrides["base"] = diff_section["base"]
        if "head" in diff_section:
            diff_overrides["head"] = diff_section["head"]
        if "custom-args" in diff_section:
            diff_overrides["custom_args"] = tuple(
                str(item)
                for item in get_sequence_from(
                    diff_section, "custom-args", base.diff.custom_args
                )
            )
        if "diff-filter" in diff_section:
            diff_overrides["diff_filter"] = str(diff_section["diff-filter"])
        if "include-untracked" in diff_section:
            diff_overrides["include_untracked"] = bool(
                diff_section["include-untracked"]
            )

        overrides["diff"] = replace(base.diff, **diff_overrides)

    return replace(base, **overrides)


def load_config(
    root: Path | None = None,
    config_path: Path | None = None,
    env_prefix: str = "TESTSIGHT_",
) -> RunnerConfig:
    """Load configuration from defaults, optional TOML, and environment variables."""

    root = find_repo_root(root)
    config = RunnerConfig(root=root)

    potential_files: list[Path] = []
    if config_path:
        potential_files.append(config_path)
    else:
        potential_files.extend(
            path
            for path in (
                root / "testsight.toml",
                root / ".testsightrc",
                root / "pyproject.toml",
            )
            if path.exists()
        )

    for path in potential_files:
        if not path.exists():
            continue
        data = _load_toml(path)
        if path.name == "pyproject.toml":
            section = (
                data.get("tool", {}).get("testsight")
                if isinstance(data.get("tool"), Mapping)
                else None
            )
        else:
            section = data.get("testsight") if isinstance(data, Mapping) else None
        if isinstance(section, Mapping):
            config = load_config_from_mapping(root, section, base=config)
            break

    # Environment overrides (simple subset to keep env usage manageable)
    env_map: dict[str, str] = {
        key[len(env_prefix) :].lower().replace("_", "-"): value
        for key, value in os.environ.items()
        if key.startswith(env_prefix)
    }

    if "test-command" in env_map:
        config = config.with_overrides(
            test_command=parse_command(env_map["test-command"])
        )

    if "dry-run" in env_map:
        config = config.with_overrides(
            dry_run=env_map["dry-run"].lower() in {"1", "true", "yes"}
        )

    if "quiet" in env_map:
        config = config.with_overrides(
            quiet=env_map["quiet"].lower() in {"1", "true", "yes"}
        )

    return config
