"""End-to-end tests for cross-file machine imports (add-machine-imports §5, §7).

Uses the committed fixture pair in tests/fixtures/imports/ (a parent that imports
a Bell-pair primitive from ./lib/) to exercise verify, Mermaid rendering, and the
import-graph view.
"""

from pathlib import Path

from q_orca.compiler.mermaid import compile_import_graph_to_mermaid, compile_to_mermaid
from q_orca.loader.import_resolver import resolve_imports
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import VerifyOptions, verify

FIXTURES = Path(__file__).parent / "fixtures" / "imports"
PARENT = FIXTURES / "parent.q.orca.md"


def _parsed_parent():
    result = parse_q_orca_markdown(PARENT.read_text())
    assert not result.errors, result.errors
    return result


def test_parent_imports_parse():
    pf = _parsed_parent().file
    assert len(pf.imports) == 1
    assert pf.imports[0].aliases == ["PrepareBellPair"]


def test_verify_follows_imports_clean():
    pf = _parsed_parent().file
    graph = resolve_imports(pf, str(PARENT))
    assert not graph.errors
    res = verify(pf.machines[0], VerifyOptions(skip_dynamic=True), file=pf, import_graph=graph)
    assert res.valid, [(e.code, e.message) for e in res.errors]


def test_no_follow_imports_leaves_child_unresolved():
    pf = _parsed_parent().file
    res = verify(pf.machines[0], VerifyOptions(skip_dynamic=True), file=pf, import_graph=None)
    assert any(e.code == "UNRESOLVED_CHILD_MACHINE" for e in res.errors)


def test_mermaid_renders_imported_child_with_path():
    pf = _parsed_parent().file
    graph = resolve_imports(pf, str(PARENT))
    mermaid = compile_to_mermaid(pf.machines[0], file=pf, import_graph=graph)
    assert "invoke: PrepareBellPair" in mermaid
    assert "state PrepareBellPair {" in mermaid
    assert "bell-pair.q.orca.md" in mermaid  # import path in the comment


def test_imports_show_renders_graph():
    pf = _parsed_parent().file
    graph = resolve_imports(pf, str(PARENT))
    view = compile_import_graph_to_mermaid(graph, root_label=PARENT.name)
    assert view.startswith("flowchart")
    assert "parent.q.orca.md" in view and "bell-pair.q.orca.md" in view
