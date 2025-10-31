"""Source analysis and indexing helpers."""

from __future__ import annotations

import ast
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, MutableMapping

from .config import RunnerConfig


@dataclass(frozen=True)
class ModuleInfo:
    name: str
    path: Path
    package_parts: tuple[str, ...]
    is_package: bool


@dataclass(frozen=True)
class ModuleData:
    exports: frozenset[str]
    imports: Mapping[str, frozenset[str | None]]


@dataclass(frozen=True)
class ModuleIndex:
    modules: Mapping[str, ModuleInfo]
    by_path: Mapping[Path, str]


class ModuleIndexer:
    """Build an importable module index for a repository."""

    def __init__(self, config: RunnerConfig):
        self.config = config

    def iter_python_files(self) -> Iterable[Path]:
        root = self.config.root
        exclude = set(self.config.exclude_dirs)
        suffixes = self.config.python_suffixes

        for dirpath, dirnames, filenames in os.walk(root):
            dirpath_path = Path(dirpath)
            try:
                relative_parts = dirpath_path.relative_to(root).parts
            except ValueError:
                # Should not happen, but guard against symlinks pointing outside.
                relative_parts = ()

            dirnames[:] = [name for name in dirnames if name not in exclude]
            if any(part in exclude for part in relative_parts):
                continue

            for filename in filenames:
                if not any(filename.endswith(suffix) for suffix in suffixes):
                    continue
                yield dirpath_path / filename

    def derive_module_name(self, path: Path) -> str | None:
        relative = path.relative_to(self.config.root)
        parts = list(relative.parts)
        for source_root in self.config.source_roots:
            if parts and parts[0] == source_root:
                parts = parts[1:]
                break
        if not parts:
            return None

        filename = parts[-1]
        if filename == "__init__.py":
            parts = parts[:-1]
        else:
            matched_suffix = None
            for suffix in sorted(self.config.python_suffixes, key=len, reverse=True):
                if suffix and filename.endswith(suffix):
                    matched_suffix = suffix
                    break
            if not matched_suffix:
                return None
            parts[-1] = filename[: -len(matched_suffix)] if matched_suffix else filename

        if not parts:
            return None
        if any(part in ("", ".") for part in parts):
            return None
        return ".".join(parts)

    def build(self) -> ModuleIndex:
        modules: MutableMapping[str, ModuleInfo] = {}
        by_path: MutableMapping[Path, str] = {}

        for path in self.iter_python_files():
            module = self.derive_module_name(path)
            if not module:
                continue
            is_package = path.name == "__init__.py"
            package_parts = (
                tuple(module.split("."))
                if is_package
                else tuple(module.split(".")[:-1])
            )
            info = ModuleInfo(
                name=module,
                path=path,
                package_parts=package_parts,
                is_package=is_package,
            )
            modules[module] = info
            by_path[path] = module

        return ModuleIndex(modules=dict(modules), by_path=dict(by_path))


def safe_parse(source: Path) -> ast.AST | None:
    try:
        text = source.read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        return None
    try:
        return ast.parse(text, filename=str(source))
    except SyntaxError:
        return None


def resolve_import_module(
    info: ModuleInfo, module: str | None, level: int
) -> str | None:
    if level == 0:
        return module

    if info.is_package:
        base_parts = list(info.name.split("."))
    else:
        base_parts = list(info.name.split(".")[:-1])

    if level > 1:
        drop = min(len(base_parts), level - 1)
        if drop:
            base_parts = base_parts[: len(base_parts) - drop]

    if module:
        base_parts.extend(module.split("."))

    result = ".".join(part for part in base_parts if part)
    return result


def analyze_module(info: ModuleInfo) -> ModuleData:
    tree = safe_parse(info.path)
    exports: set[str] = set()
    imports: dict[str, set[str | None]] = {}

    if tree is None:
        return ModuleData(frozenset(exports), {})

    def add_import(target_module: str | None, symbol: str | None) -> None:
        if not target_module:
            return
        imports.setdefault(target_module, set()).add(symbol)

    for node in ast.walk(tree):
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            exports.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    exports.add(target.id)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                binding = alias.asname or alias.name.split(".")[0]
                add_import(alias.name, None)
                if binding:
                    exports.add(binding)
        elif isinstance(node, ast.ImportFrom):
            target_module = resolve_import_module(info, node.module, node.level or 0)
            if not target_module:
                continue
            for alias in node.names:
                if alias.name == "*":
                    add_import(target_module, None)
                    continue
                binding = alias.asname or alias.name
                add_import(target_module, binding)
                exports.add(binding)

    frozen_imports = {module: frozenset(symbols) for module, symbols in imports.items()}
    return ModuleData(exports=frozenset(exports), imports=frozen_imports)


def build_module_data(
    index: ModuleIndex,
) -> tuple[dict[str, ModuleData], dict[str, dict[str | None, set[str]]]]:
    data: dict[str, ModuleData] = {}
    reverse: dict[str, dict[str | None, set[str]]] = {}

    for module_name, info in index.modules.items():
        module_data = analyze_module(info)
        imports_mutable: dict[str, set[str | None]] = {
            target: set(symbols) for target, symbols in module_data.imports.items()
        }

        for target_module, symbols in list(imports_mutable.items()):
            for symbol in list(symbols):
                if symbol is None:
                    continue
                candidate = f"{target_module}.{symbol}"
                if candidate in index.modules:
                    imports_mutable.setdefault(candidate, set()).add(None)

        augmented_imports = {
            module: frozenset(symbols) for module, symbols in imports_mutable.items()
        }
        module_data = ModuleData(exports=module_data.exports, imports=augmented_imports)
        data[module_name] = module_data

        for target_module, symbols in module_data.imports.items():
            for symbol in symbols or {None}:
                reverse.setdefault(target_module, {}).setdefault(symbol, set()).add(
                    module_name
                )

    return data, reverse


__all__ = [
    "ModuleInfo",
    "ModuleData",
    "ModuleIndex",
    "ModuleIndexer",
    "analyze_module",
    "build_module_data",
]
