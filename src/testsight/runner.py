"""Public runner orchestration for Testsight."""

from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

from .config import DiffSource, RunnerConfig
from .indexer import ModuleIndexer
from .resolver import ImpactAnalysis, ImpactResolver, prepare_analysis


class ChangeDetectionError(RuntimeError):
    """Raised when git diff inspection fails."""


@dataclass
class ChangeDetector:
    config: RunnerConfig

    def collect(self) -> list[Path]:
        mode = self.config.diff.mode
        root = self.config.root
        paths: list[Path] = []

        if mode is DiffSource.STAGED:
            args = [
                "git",
                "diff",
                "--name-only",
                "--cached",
                f"--diff-filter={self.config.diff.diff_filter}",
            ]
        elif mode is DiffSource.UNSTAGED:
            args = [
                "git",
                "diff",
                "--name-only",
                f"--diff-filter={self.config.diff.diff_filter}",
            ]
        elif mode is DiffSource.RANGE:
            base = self.config.diff.base
            head = self.config.diff.head
            if not base or not head:
                raise ChangeDetectionError(
                    "Diff mode 'range' requires both base and head revisions"
                )
            args = [
                "git",
                "diff",
                "--name-only",
                f"--diff-filter={self.config.diff.diff_filter}",
                f"{base}..{head}",
            ]
        elif mode is DiffSource.CUSTOM:
            custom = list(self.config.diff.custom_args)
            if not custom:
                raise ChangeDetectionError(
                    "Custom diff mode requires explicit git arguments"
                )
            args = ["git", "diff", *custom]
            if "--name-only" not in custom:
                args.insert(2, "--name-only")
            if not any(arg.startswith("--diff-filter") for arg in custom):
                args.insert(2, f"--diff-filter={self.config.diff.diff_filter}")
        else:  # pragma: no cover - defensive programming
            raise ChangeDetectionError(f"Unsupported diff mode: {mode}")

        result = subprocess.run(
            args,
            cwd=root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode not in (0, 1):
            raise ChangeDetectionError(
                result.stderr.strip() or "Failed to execute git diff"
            )

        for line in result.stdout.splitlines():
            entry = line.strip()
            if not entry:
                continue
            path = (root / entry).resolve()
            if not path.exists():
                continue
            if not any(
                path.name.endswith(suffix) for suffix in self.config.python_suffixes
            ):
                continue
            paths.append(path)

        if self.config.diff.include_untracked:
            ls_files = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=root,
                text=True,
                capture_output=True,
                check=False,
            )
            if ls_files.returncode not in (0, 1):
                raise ChangeDetectionError(
                    ls_files.stderr.strip() or "Failed to list untracked files"
                )
            for line in ls_files.stdout.splitlines():
                entry = line.strip()
                if not entry:
                    continue
                path = (root / entry).resolve()
                if not path.exists():
                    continue
                if not any(
                    path.name.endswith(suffix) for suffix in self.config.python_suffixes
                ):
                    continue
                paths.append(path)

        unique: list[Path] = []
        seen: set[Path] = set()
        for path in paths:
            if path in seen:
                continue
            seen.add(path)
            unique.append(path)
        return unique


class TestsightRunner:
    """High-level interface combining change detection, impact analysis and execution."""

    __test__ = False  # Prevent pytest from collecting this class as a test.

    def __init__(self, config: RunnerConfig):
        self.config = config
        self.indexer = ModuleIndexer(config)

    def collect_changes(self) -> list[Path]:
        detector = ChangeDetector(self.config)
        return detector.collect()

    def plan(self, changed_paths: Sequence[Path] | None = None) -> list[Path]:
        paths = (
            list(changed_paths) if changed_paths is not None else self.collect_changes()
        )
        index = self.indexer.build()
        analysis = prepare_analysis(index)
        resolver = ImpactResolver(self.config, index, analysis)
        return resolver.resolve(paths)

    def execute(self, tests: Sequence[Path]) -> int:
        if not tests:
            if not self.config.quiet:
                print("Testsight: no impacted tests detected.")
            return 0

        if not self.config.quiet:
            rel = [
                str(path.relative_to(self.config.root))
                if path.is_relative_to(self.config.root)
                else str(path)
                for path in tests
            ]
            print("Impacted test modules (" + str(len(rel)) + "):")
            for item in rel:
                print(f"  - {item}")

        if self.config.dry_run:
            return 0

        command = list(self.config.test_command) + [
            str(path.relative_to(self.config.root))
            if path.is_relative_to(self.config.root)
            else str(path)
            for path in tests
        ]
        if self.config.print_command and not self.config.quiet:
            print("Running:", " ".join(command))

        env = os.environ.copy()
        if self.config.env:
            env.update(self.config.env)

        completed = subprocess.run(command, cwd=self.config.root, env=env)
        return completed.returncode

    def run(self, changed_paths: Sequence[Path] | None = None) -> int:
        tests = self.plan(changed_paths)
        return self.execute(tests)


__all__ = [
    "TestsightRunner",
    "ChangeDetector",
    "ChangeDetectionError",
    "ImpactAnalysis",
]
