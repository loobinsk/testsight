"""Command-line interface for Testsight."""

from __future__ import annotations

import argparse
import json
import shlex
import sys
from dataclasses import replace
from pathlib import Path
from typing import Sequence

from . import __version__
from .config import DiffSource, RunnerConfig, load_config, parse_command
from .runner import ChangeDetectionError, TestsightRunner


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testsight",
        description="Run only the pytest modules impacted by recent changes.",
    )
    parser.add_argument(
        "--config", type=Path, help="Path to testsight TOML configuration file."
    )
    parser.add_argument(
        "--root",
        type=Path,
        help="Repository root (defaults to auto-detected git root).",
    )
    parser.add_argument(
        "--diff-mode",
        choices=[mode.value for mode in DiffSource],
        help="Source of changed files (staged, unstaged, range, custom).",
    )
    parser.add_argument("--base", help="Base revision used for diff range mode.")
    parser.add_argument("--head", help="Head revision used for diff range mode.")
    parser.add_argument(
        "--diff-args",
        help="Explicit arguments passed to `git diff` (space separated, implies --diff-mode=custom).",
    )
    parser.add_argument(
        "--include-untracked",
        action="store_true",
        help="Include untracked files when gathering impacted tests.",
    )
    parser.add_argument(
        "--test-command", help="Shell-style command used to execute tests."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Plan impacted tests without running them.",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="Alias for --dry-run (prints impacted test list).",
    )
    parser.add_argument(
        "--json", action="store_true", help="Output impacted tests as JSON and exit."
    )
    parser.add_argument(
        "--quiet", action="store_true", help="Suppress informational output."
    )
    parser.add_argument(
        "--no-print-command",
        action="store_true",
        help="Do not echo the test command before execution.",
    )
    parser.add_argument(
        "--min-token-length",
        type=int,
        help="Minimum length for fallback token matching.",
    )
    parser.add_argument(
        "--fallback-score",
        type=int,
        help="Minimum score required for fallback matching.",
    )
    parser.add_argument(
        "--source-root",
        action="append",
        dest="source_roots",
        help="Custom source root directory (can be specified multiple times).",
    )
    parser.add_argument(
        "--exclude-dir",
        action="append",
        dest="exclude_dirs",
        help="Directory name to exclude from indexing (can be specified multiple times).",
    )
    parser.add_argument(
        "--test-dir",
        action="append",
        dest="test_dir_markers",
        help="Directory marker treated as containing tests.",
    )
    parser.add_argument(
        "--test-prefix",
        action="append",
        dest="test_prefixes",
        help="Filename prefix recognised as a test module.",
    )
    parser.add_argument(
        "--test-suffix",
        action="append",
        dest="test_suffixes",
        help="Filename suffix recognised as a test module.",
    )
    parser.add_argument(
        "--stopword",
        action="append",
        dest="stopwords",
        help="Additional token stopword to ignore during fallback matching.",
    )
    parser.add_argument(
        "--env",
        action="append",
        metavar="KEY=VALUE",
        help="Additional environment variable passed to the test command.",
    )
    parser.add_argument(
        "--version", action="store_true", help="Show Testsight version and exit."
    )
    parser.add_argument(
        "paths",
        nargs="*",
        help="Explicit paths to treat as changed (for scripting/testing).",
    )
    return parser


def apply_cli_overrides(config: RunnerConfig, args: argparse.Namespace) -> RunnerConfig:
    overrides: dict[str, object] = {}

    if args.test_command:
        overrides["test_command"] = parse_command(args.test_command)

    if args.dry_run or args.list:
        overrides["dry_run"] = True
    if args.quiet:
        overrides["quiet"] = True
    if args.no_print_command:
        overrides["print_command"] = False

    if args.source_roots:
        overrides["source_roots"] = tuple(args.source_roots)
    if args.exclude_dirs:
        overrides["exclude_dirs"] = tuple(args.exclude_dirs)

    if args.env:
        current = dict(config.env) if config.env else {}
        for entry in args.env:
            key, sep, value = entry.partition("=")
            if not sep:
                raise SystemExit(f"Invalid --env value '{entry}', expected KEY=VALUE")
            current[key] = value
        overrides["env"] = current

    if overrides:
        config = config.with_overrides(**overrides)

    naming_updates: dict[str, object] = {}
    if args.test_dir_markers:
        naming_updates["directory_markers"] = tuple(args.test_dir_markers)
    if args.test_prefixes:
        naming_updates["filename_prefixes"] = tuple(args.test_prefixes)
    if args.test_suffixes:
        naming_updates["filename_suffixes"] = tuple(args.test_suffixes)
    if naming_updates:
        config = config.with_overrides(naming=replace(config.naming, **naming_updates))

    token_updates: dict[str, object] = {}
    if args.min_token_length is not None:
        token_updates["minimum_length"] = args.min_token_length
    if args.fallback_score is not None:
        token_updates["fallback_score"] = args.fallback_score
    if args.stopwords:
        token_updates["stopwords"] = tuple(
            dict.fromkeys((*config.tokens.stopwords, *args.stopwords))
        )
    if token_updates:
        config = config.with_overrides(tokens=replace(config.tokens, **token_updates))

    diff = config.diff
    if args.diff_mode:
        diff = replace(diff, mode=DiffSource(args.diff_mode))
    if args.base:
        diff = replace(diff, base=args.base)
    if args.head:
        diff = replace(diff, head=args.head)
    if args.diff_args:
        diff_args = tuple(shlex.split(args.diff_args))
        diff = replace(diff, mode=DiffSource.CUSTOM, custom_args=diff_args)
    if args.include_untracked:
        diff = replace(diff, include_untracked=True)
    config = config.with_overrides(diff=diff)

    return config


def resolve_changed_paths(
    args: argparse.Namespace, config: RunnerConfig
) -> list[Path] | None:
    if not args.paths:
        return None
    resolved: list[Path] = []
    for entry in args.paths:
        candidate = Path(entry)
        path = (
            candidate
            if candidate.is_absolute()
            else (config.root / candidate).resolve()
        )
        if not path.exists():
            print(f"warning: explicit path '{entry}' does not exist", file=sys.stderr)
            continue
        resolved.append(path)
    return resolved


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.version:
        print(__version__)
        return 0

    root = args.root
    config = load_config(root=root, config_path=args.config)
    config = apply_cli_overrides(config, args)

    explicit_paths = resolve_changed_paths(args, config)

    runner = TestsightRunner(config)

    try:
        if args.json:
            tests = runner.plan(explicit_paths)
            payload = [
                str(path.relative_to(config.root))
                if path.is_relative_to(config.root)
                else str(path)
                for path in tests
            ]
            print(json.dumps(payload, ensure_ascii=False, indent=2))
            return 0

        if config.dry_run:
            tests = runner.plan(explicit_paths)
            return runner.execute(tests)

        if explicit_paths is not None:
            return runner.run(explicit_paths)
        return runner.run()
    except ChangeDetectionError as exc:
        print(f"Testsight: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
