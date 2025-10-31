"""Impact analysis for targeted test execution."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping, Sequence

from .config import RunnerConfig
from .indexer import ModuleData, ModuleIndex, ModuleInfo


class TokenCollector:
    """Extract path tokens used by the fallback matcher."""

    def __init__(self, root: Path, config: RunnerConfig):
        self.root = root
        self.config = config

    def _split_token(self, token: str) -> set[str]:
        token = token.replace("-", "_")
        parts: list[str] = []
        for raw in token.split("_"):
            if not raw:
                continue
            camel_parts: list[str] = []
            start = 0
            for idx in range(1, len(raw)):
                if raw[idx].isupper() and (
                    raw[idx - 1].islower()
                    or (idx + 1 < len(raw) and raw[idx + 1].islower())
                ):
                    camel_parts.append(raw[start:idx].lower())
                    start = idx
            camel_parts.append(raw[start:].lower())
            parts.extend(camel_parts)
        tokens = set(parts)
        tokens.add(token.lower())
        tokens.update(p[:-1] for p in parts if len(p) > 4 and p.endswith("s"))
        minimum = self.config.tokens.minimum_length
        stopwords = set(self.config.tokens.stopwords)
        return {t for t in tokens if len(t) >= minimum and t not in stopwords}

    def path_tokens(self, path: Path) -> frozenset[str]:
        tokens: set[str] = set()
        try:
            parts = path.relative_to(self.root).parts
        except ValueError:
            parts = path.parts
        for part in parts:
            base = part.split(".")[0]
            tokens.update(self._split_token(base))
        return frozenset(tokens)

    def directory_tokens(self, path: Path) -> frozenset[str]:
        tokens: set[str] = set()
        try:
            parts = path.relative_to(self.root).parts[:-1]
        except ValueError:
            parts = path.parts[:-1]
        for part in parts:
            base = part.split(".")[0]
            tokens.update(self._split_token(base))
        return frozenset(tokens)


@dataclass
class ImpactAnalysis:
    modules: Mapping[str, ModuleInfo]
    module_data: Mapping[str, ModuleData]
    reverse_imports: Mapping[str, Mapping[str | None, set[str]]]


class ImpactResolver:
    """Compute the set of impacted test modules."""

    def __init__(
        self, config: RunnerConfig, index: ModuleIndex, analysis: ImpactAnalysis
    ):
        self.config = config
        self.index = index
        self.analysis = analysis
        self.tokenizer = TokenCollector(config.root, config)
        self.test_tokens = {
            info.path: self.tokenizer.path_tokens(info.path)
            for info in index.modules.values()
            if self._is_test_module(info)
        }
        self.test_dir_tokens = {
            path: self.tokenizer.directory_tokens(path) for path in self.test_tokens
        }

    def _is_test_module(self, info: ModuleInfo) -> bool:
        return self.config.naming.is_test_file(
            info.path,
            self.config.root,
            self.config.python_suffixes,
        )

    def resolve(self, changed_paths: Sequence[Path]) -> list[Path]:
        if not changed_paths:
            return []

        by_path = self.index.by_path
        modules = self.index.modules
        module_data = self.analysis.module_data
        reverse_imports = self.analysis.reverse_imports

        changed_modules = {by_path[path] for path in changed_paths if path in by_path}

        impacted_modules: set[str] = set()

        if changed_modules:
            queue: deque[tuple[str, str | None]] = deque()
            for module in changed_modules:
                data = module_data.get(module)
                if data:
                    for symbol in data.exports:
                        queue.append((module, symbol))
                queue.append((module, None))

            visited: set[tuple[str, str | None]] = set()
            while queue:
                module, symbol = queue.popleft()
                if (module, symbol) in visited:
                    continue
                visited.add((module, symbol))

                info = modules.get(module)
                if info and self._is_test_module(info):
                    impacted_modules.add(module)
                    continue

                reverse = reverse_imports.get(module, {})
                if symbol is None:
                    dependants = reverse.get(None, set())
                else:
                    dependants = set(reverse.get(symbol, set()))
                    dependants.update(reverse.get(None, set()))

                for dependant in dependants:
                    dep_data = module_data.get(dependant)
                    if not dep_data:
                        continue
                    imported_symbols = dep_data.imports.get(module, frozenset())

                    if symbol is None:
                        if None in imported_symbols:
                            queue.append((dependant, None))
                    else:
                        if symbol in imported_symbols:
                            queue.append((dependant, symbol))
                        if None in imported_symbols:
                            queue.append((dependant, None))

        fallback_threshold = self.config.tokens.fallback_score
        if fallback_threshold <= 0:
            fallback_threshold = 1

        staged_tokens = [self.tokenizer.path_tokens(path) for path in changed_paths]
        staged_dir_tokens = [
            self.tokenizer.directory_tokens(path) for path in changed_paths
        ]

        for path, tokens in self.test_tokens.items():
            if path not in by_path:
                continue
            scores = [
                sum(len(token) for token in tokens.intersection(staged))
                for staged in staged_tokens
            ]
            score = max(scores) if scores else 0
            if score < fallback_threshold:
                continue

            dir_match = any(
                self.test_dir_tokens.get(path, frozenset()).intersection(dir_tokens)
                for dir_tokens in staged_dir_tokens
            )
            if not dir_match:
                continue
            module_name = by_path.get(path)
            if module_name:
                impacted_modules.add(module_name)

        return sorted(
            modules[module].path
            for module in impacted_modules
            if module in modules and self._is_test_module(modules[module])
        )


def prepare_analysis(index: ModuleIndex) -> ImpactAnalysis:
    from .indexer import build_module_data

    module_data, reverse_imports = build_module_data(index)
    return ImpactAnalysis(
        modules=index.modules,
        module_data=module_data,
        reverse_imports=reverse_imports,
    )


__all__ = ["ImpactResolver", "ImpactAnalysis", "prepare_analysis"]
