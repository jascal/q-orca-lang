"""Tests for the cross-file import resolver (add-machine-imports §3.5)."""

from q_orca.loader.import_resolver import resolve_imports
from q_orca.parser.markdown_parser import parse_q_orca_markdown

_CHILD = """# machine PrepareBellPair
## context
| Field | Type | Default |
| seed | int | 0 |
## state |a> [initial]
## state |b> [final]
## transitions
| Source | Event | Guard | Target | Action |
| |a> | g | | |b> | |
"""


def _write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text)
    return path


def _graph(parent_src, parent_path):
    file_def = parse_q_orca_markdown(parent_src).file
    return resolve_imports(file_def, str(parent_path))


def test_happy_path_relative_import(tmp_path):
    _write(tmp_path / "lib" / "bell-pair.q.orca.md", _CHILD)
    parent = (
        "# machine Parent\n## imports\n| Path | Aliases |\n"
        "| ./lib/bell-pair.q.orca.md | PrepareBellPair |\n"
        "## state |i> [initial]\n## state |d> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n| |i> | g | | |d> | |\n"
    )
    _write(tmp_path / "parent.q.orca.md", parent)
    g = _graph(parent, tmp_path / "parent.q.orca.md")
    assert not g.errors
    assert g.lookup_machine("PrepareBellPair").name == "PrepareBellPair"
    assert g.known_aliases() == {"PrepareBellPair"}


def test_project_relative_import(tmp_path):
    _write(tmp_path / "pyproject.toml", "[project]\nname='x'\n")
    _write(tmp_path / "lib" / "bell-pair.q.orca.md", _CHILD)
    parent = (
        "# machine Parent\n## imports\n| Path | Aliases |\n"
        "| q_orca:lib/bell-pair.q.orca.md | PrepareBellPair |\n"
        "## state |i> [initial]\n## state |d> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n| |i> | g | | |d> | |\n"
    )
    # parent lives in a nested dir; project root is found by walking up to pyproject.toml
    ppath = _write(tmp_path / "nested" / "parent.q.orca.md", parent)
    g = _graph(parent, ppath)
    assert not g.errors, g.errors
    assert g.lookup_machine("PrepareBellPair") is not None


def test_missing_file(tmp_path):
    parent = (
        "# machine Parent\n## imports\n| Path | Aliases |\n"
        "| ./lib/missing.q.orca.md | X |\n"
        "## state |i> [initial]\n## state |d> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n| |i> | g | | |d> | |\n"
    )
    _write(tmp_path / "parent.q.orca.md", parent)
    g = _graph(parent, tmp_path / "parent.q.orca.md")
    assert any(e.code == "IMPORT_NOT_FOUND" for e in g.errors)


def test_import_cycle(tmp_path):
    a = (
        "# machine A\n## imports\n| Path | Aliases |\n| ./b.q.orca.md | B |\n"
        "## state |a0> [initial]\n## state |a1> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n| |a0> | g | | |a1> | |\n"
    )
    b = (
        "# machine B\n## imports\n| Path | Aliases |\n| ./a.q.orca.md | A |\n"
        "## state |b0> [initial]\n## state |b1> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n| |b0> | g | | |b1> | |\n"
    )
    _write(tmp_path / "a.q.orca.md", a)
    _write(tmp_path / "b.q.orca.md", b)
    g = _graph(a, tmp_path / "a.q.orca.md")
    assert any(e.code == "IMPORT_CYCLE" for e in g.errors)


def test_reexport_via_index(tmp_path):
    _write(tmp_path / "lib" / "bell-pair.q.orca.md", _CHILD)
    index = (
        "# machine Index\n## imports\n| Path | Aliases |\n"
        "| ./bell-pair.q.orca.md | PrepareBellPair |\n"
        "## reexports\n| Alias | From |\n| PrepareBellPair | (this file) |\n"
        "## state |i> [initial]\n## state |j> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n| |i> | g | | |j> | |\n"
    )
    _write(tmp_path / "lib" / "index.q.orca.md", index)
    consumer = (
        "# machine Consumer\n## imports\n| Path | Aliases |\n"
        "| ./lib/index.q.orca.md | PrepareBellPair |\n"
        "## state |c> [initial]\n## state |d> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n| |c> | g | | |d> | |\n"
    )
    _write(tmp_path / "consumer.q.orca.md", consumer)
    g = _graph(consumer, tmp_path / "consumer.q.orca.md")
    assert not g.errors, g.errors
    assert g.lookup_machine("PrepareBellPair").name == "PrepareBellPair"


def test_reexport_chain_too_deep(tmp_path):
    # base imports r0; r0..r6 each re-export PrepareBellPair from the next file;
    # m defines it. The re-export descent exceeds the 4-hop cap before reaching m.
    _write(tmp_path / "m.q.orca.md", _CHILD)
    hops = [f"r{i}" for i in range(7)]
    targets = [f"r{i + 1}" for i in range(6)] + ["m"]
    for name, tgt in zip(hops, targets):
        src = (
            f"# machine {name.upper()}\n## imports\n| Path | Aliases |\n"
            f"| ./{tgt}.q.orca.md | PrepareBellPair |\n"
            "## reexports\n| Alias | From |\n| PrepareBellPair | (this file) |\n"
            f"## state |{name}0> [initial]\n## state |{name}1> [final]\n"
            f"## transitions\n| Source | Event | Guard | Target | Action |\n| |{name}0> | g | | |{name}1> | |\n"
        )
        _write(tmp_path / f"{name}.q.orca.md", src)
    base = (
        "# machine Base\n## imports\n| Path | Aliases |\n"
        "| ./r0.q.orca.md | PrepareBellPair |\n"
        "## state |b0> [initial]\n## state |b1> [final]\n"
        "## transitions\n| Source | Event | Guard | Target | Action |\n| |b0> | g | | |b1> | |\n"
    )
    _write(tmp_path / "base.q.orca.md", base)
    g = _graph(base, tmp_path / "base.q.orca.md")
    assert any(e.code == "IMPORT_CHAIN_TOO_DEEP" for e in g.errors), [e.code for e in g.errors]
