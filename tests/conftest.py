from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import pytest

from testsight.config import RunnerConfig, load_config


@dataclass
class RepoHelper:
    root: Path

    def git(self, *args: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.run(
            ["git", *args],
            cwd=self.root,
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            raise RuntimeError(f"git {' '.join(args)} failed: {result.stderr}")
        return result

    def write(self, relative: str, content: str) -> Path:
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return path

    def stage(self, *paths: str) -> None:
        self.git("add", *paths)

    def remove(self, *paths: str) -> None:
        self.git("rm", "-f", *paths)

    def commit(self, message: str = "feat: initial") -> None:
        self.git("commit", "-m", message)

    def runner_config(self, **overrides: object) -> RunnerConfig:
        config = load_config(root=self.root)
        if overrides:
            config = config.with_overrides(**overrides)
        return config


@pytest.fixture
def repo(tmp_path: Path) -> Iterable[RepoHelper]:
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(
        ["git", "init"], cwd=root, check=True, text=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Testsight"], cwd=root, check=True, text=True
    )
    subprocess.run(
        ["git", "config", "user.email", "testsight@example.com"],
        cwd=root,
        check=True,
        text=True,
    )

    helper = RepoHelper(root)
    yield helper
