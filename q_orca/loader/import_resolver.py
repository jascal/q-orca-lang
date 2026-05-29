"""Cross-file import resolution (`add-machine-imports`).

`resolve_imports(file_def, base_path)` walks a file's `## imports` graph, parses
each reachable file once, detects cycles, and returns a `ResolvedImportGraph`
that the composition verifier consults to resolve `invoke: Child(...)` against
machines defined in other files. The parser stays filesystem-free; all disk I/O
lives here.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from typing import Optional

from q_orca.ast import QMachineDef, QOrcaFile

_MAX_REEXPORT_HOPS = 4


@dataclass
class ImportDiagnostic:
    code: str
    message: str


@dataclass
class ResolvedImportGraph:
    """Resolved cross-file imports for one importing file."""
    machines_by_alias: dict[str, QMachineDef] = field(default_factory=dict)
    # alias -> list of distinct source paths it resolved from (for ambiguity)
    alias_sources: dict[str, list[str]] = field(default_factory=dict)
    errors: list[ImportDiagnostic] = field(default_factory=list)
    # (importer_abs, imported_abs) edges for the import-graph view
    import_edges: list[tuple[str, str]] = field(default_factory=list)

    def lookup_machine(self, alias: str) -> Optional[QMachineDef]:
        return self.machines_by_alias.get(alias)

    def known_aliases(self) -> set[str]:
        return set(self.machines_by_alias)

    def is_ambiguous(self, alias: str) -> bool:
        return len(set(self.alias_sources.get(alias, []))) > 1


def find_project_root(start_path: str) -> str:
    """Nearest ancestor directory containing `pyproject.toml`, else the cwd."""
    d = os.path.dirname(os.path.abspath(start_path))
    while True:
        if os.path.isfile(os.path.join(d, "pyproject.toml")):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return os.getcwd()
        d = parent


def _resolve_path(raw: str, base_dir: str, project_root: str) -> Optional[str]:
    """Map an import `Path` to an absolute path; None for an absolute/invalid one."""
    if raw.startswith("q_orca:"):
        return os.path.normpath(os.path.join(project_root, raw[len("q_orca:"):]))
    if raw.startswith("/") or re.match(r"^[A-Za-z]:[\\/]", raw):
        return None  # absolute — rejected (also caught at parse time)
    return os.path.normpath(os.path.join(base_dir, raw))


def resolve_imports(
    file_def: QOrcaFile, base_path: str, project_root: Optional[str] = None
) -> ResolvedImportGraph:
    graph = ResolvedImportGraph()
    root = project_root or find_project_root(base_path)
    base_abs = os.path.abspath(base_path)
    parsed: dict[str, Optional[QOrcaFile]] = {base_abs: file_def}

    def parse_file(path_abs: str, chain: list[str]) -> Optional[QOrcaFile]:
        if path_abs in parsed:
            return parsed[path_abs]
        from q_orca.parser.markdown_parser import parse_q_orca_markdown
        try:
            with open(path_abs, "r", encoding="utf-8") as fh:
                result = parse_q_orca_markdown(fh.read())
        except OSError:
            parsed[path_abs] = None
            return None
        if result.errors:
            graph.errors.append(ImportDiagnostic(
                "IMPORT_PARSE_FAILED",
                f"{_render_chain(chain + [path_abs])}: {result.errors[0]}",
            ))
            parsed[path_abs] = None
            return None
        parsed[path_abs] = result.file
        return result.file

    # 1. Traverse the whole import graph: parse reachable files, detect cycles,
    #    record edges. DFS with a path stack for back-edge (cycle) detection.
    def traverse(f: QOrcaFile, f_abs: str, stack: list[str]) -> None:
        base_dir = os.path.dirname(f_abs)
        for imp in f.imports:
            tgt = _resolve_path(imp.path, base_dir, root)
            if tgt is None or not os.path.isfile(tgt):
                graph.errors.append(ImportDiagnostic(
                    "IMPORT_NOT_FOUND",
                    f"import path '{imp.path}' (from {os.path.basename(f_abs)}) "
                    f"does not resolve to a file",
                ))
                continue
            graph.import_edges.append((f_abs, tgt))
            if tgt in stack:
                cycle = stack[stack.index(tgt):] + [tgt]
                graph.errors.append(ImportDiagnostic(
                    "IMPORT_CYCLE", "import cycle: " + _render_chain(cycle)))
                continue
            already = tgt in parsed
            sub = parse_file(tgt, stack)
            if sub is not None and not already:
                traverse(sub, tgt, stack + [tgt])

    traverse(file_def, base_abs, [base_abs])

    # 2. Bind each alias declared in the importing file's imports.
    base_dir = os.path.dirname(base_abs)
    for imp in file_def.imports:
        tgt = _resolve_path(imp.path, base_dir, root)
        if tgt is None or parsed.get(tgt) is None:
            continue
        for alias in imp.aliases:
            machine = _resolve_alias(parsed[tgt], tgt, alias, root, [base_abs, tgt], 0, graph)
            if machine is not None:
                graph.machines_by_alias[alias] = machine
                sources = graph.alias_sources.setdefault(alias, [])
                if tgt not in sources:
                    sources.append(tgt)

    return graph


def _resolve_alias(
    f: QOrcaFile,
    f_abs: str,
    alias: str,
    project_root: str,
    chain: list[str],
    depth: int,
    graph: ResolvedImportGraph,
) -> Optional[QMachineDef]:
    """Resolve `alias` to a machine in `f` directly, or via `f`'s re-exports."""
    if depth > _MAX_REEXPORT_HOPS:
        graph.errors.append(ImportDiagnostic(
            "IMPORT_CHAIN_TOO_DEEP",
            f"re-export chain for '{alias}' exceeds {_MAX_REEXPORT_HOPS} hops: "
            f"{_render_chain(chain)}",
        ))
        return None

    for m in f.machines:
        if m.name == alias:
            return m

    if any(rx.alias == alias for rx in f.reexports):
        base_dir = os.path.dirname(f_abs)
        for imp in f.imports:
            tgt = _resolve_path(imp.path, base_dir, project_root)
            if tgt is None or not os.path.isfile(tgt) or tgt in chain:
                continue
            from q_orca.parser.markdown_parser import parse_q_orca_markdown
            try:
                with open(tgt, "r", encoding="utf-8") as fh:
                    sub = parse_q_orca_markdown(fh.read())
            except OSError:
                continue
            if sub.errors:
                continue
            found = _resolve_alias(
                sub.file, tgt, alias, project_root, chain + [tgt], depth + 1, graph)
            if found is not None:
                return found
    return None


def _render_chain(paths: list[str]) -> str:
    return " → ".join(os.path.basename(p) for p in paths)
