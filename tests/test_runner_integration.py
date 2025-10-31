from __future__ import annotations

import json
import subprocess
from dataclasses import replace

import pytest

from testsight.cli import main as cli_main
from testsight.config import DiffSource
from testsight.runner import ChangeDetector, TestsightRunner


@pytest.fixture
def seeded_repo(repo):
    repo.write("src/app/__init__.py", "")
    repo.write(
        "src/app/service.py",
        """
from app import util

def get_answer():
    return util.adjust(41)
""".strip()
        + "\n",
    )
    repo.write(
        "src/app/util.py",
        """
def adjust(value):
    return value + 1
""".strip()
        + "\n",
    )
    repo.write(
        "tests/app/test_service.py",
        """
from app import service

def test_get_answer():
    assert service.get_answer() == 42
""".strip()
        + "\n",
    )
    repo.stage(".")
    repo.commit("chore: initial layout")
    return repo


def test_runner_plan_with_staged_change(seeded_repo):
    repo = seeded_repo
    repo.write("src/app/util.py", "def adjust(value):\n    return value + 2\n")
    repo.stage("src/app/util.py")

    runner = TestsightRunner(repo.runner_config(dry_run=True))
    tests = runner.plan()
    assert repo.root / "tests/app/test_service.py" in tests


def test_runner_plan_handles_multiple_changes(seeded_repo):
    repo = seeded_repo
    repo.write(
        "src/app/service.py", "from app import util\n\nvalue = util.adjust(40)\n"
    )
    repo.write("tests/app/test_extra.py", "def test_extra():\n    assert True\n")
    repo.stage("src/app/service.py")
    repo.stage("tests/app/test_extra.py")

    runner = TestsightRunner(repo.runner_config(dry_run=True))
    tests = runner.plan()
    assert set(tests) >= {
        repo.root / "tests/app/test_service.py",
        repo.root / "tests/app/test_extra.py",
    }


def test_runner_plan_returns_empty_without_changes(seeded_repo):
    runner = TestsightRunner(seeded_repo.runner_config(dry_run=True))
    assert runner.plan() == []


def test_runner_run_with_explicit_paths(seeded_repo, monkeypatch):
    repo = seeded_repo
    repo.write("src/app/util.py", "def adjust(value):\n    return value + 5\n")

    calls = []

    def fake_run(cmd, cwd=None, env=None):
        calls.append(cmd)

        class Result:
            returncode = 0

        return Result()

    monkeypatch.setattr(subprocess, "run", fake_run)

    runner = TestsightRunner(repo.runner_config())
    tests = runner.plan([repo.root / "src/app/util.py"])
    assert tests
    code = runner.execute(tests)
    assert code == 0
    assert calls
    assert repo.root / "tests/app/test_service.py" in tests


def test_change_detector_range_mode(seeded_repo):
    repo = seeded_repo
    repo.write("src/app/util.py", "def adjust(value):\n    return value + 3\n")
    repo.stage("src/app/util.py")
    repo.commit("feat: tweak util")

    repo.write(
        "src/app/service.py", "from app import util\n\nvalue = util.adjust(10)\n"
    )
    repo.stage("src/app/service.py")
    repo.commit("feat: adjust service")

    base_config = repo.runner_config()
    diff = replace(base_config.diff, mode=DiffSource.RANGE, base="HEAD^", head="HEAD")
    config = base_config.with_overrides(diff=diff)

    detector = ChangeDetector(config)
    paths = detector.collect()
    assert any(path.name == "service.py" for path in paths)


def test_cli_json_output(seeded_repo, capsys):
    repo = seeded_repo
    repo.write("src/app/util.py", "def adjust(value):\n    return value + 10\n")
    repo.stage("src/app/util.py")
    code = cli_main(["--root", str(repo.root), "--json"])
    assert code == 0
    captured = capsys.readouterr().out
    data = json.loads(captured)
    assert "tests/app/test_service.py" in data


def test_cli_dry_run_lists_tests(seeded_repo, capsys):
    repo = seeded_repo
    repo.write(
        "src/app/service.py", "from app import util\n\nvalue = util.adjust(12)\n"
    )
    repo.stage("src/app/service.py")
    code = cli_main(["--root", str(repo.root), "--dry-run"])
    assert code == 0
    output = capsys.readouterr().out
    assert "Impacted test modules" in output


def test_cli_explicit_paths(seeded_repo):
    repo = seeded_repo
    code = cli_main(
        [
            "--root",
            str(repo.root),
            "--dry-run",
            str(repo.root / "src/app/service.py"),
        ]
    )
    assert code == 0


def test_change_detector_includes_untracked(seeded_repo):
    repo = seeded_repo
    repo.write("src/app/new_module.py", "def hello():\n    return 'hi'\n")

    base_config = repo.runner_config()
    diff = replace(base_config.diff, include_untracked=True)
    config = base_config.with_overrides(diff=diff)
    detector = ChangeDetector(config)
    paths = detector.collect()
    assert any(path.name == "new_module.py" for path in paths)
