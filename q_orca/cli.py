"""Q-Orca CLI — command-line interface."""

import argparse
import json
import sys
from pathlib import Path

from q_orca import __version__
from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.compiler.mermaid import compile_to_mermaid
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from q_orca.compiler.cudaq import compile_to_cudaq
from q_orca.compiler.util import ComposedMachineError
from q_orca.runtime.python import check_python_dependencies, simulate_machine
from q_orca.runtime.types import QIterativeSimulationResult
from q_orca.tools import Q_ORCA_TOOLS


def main():
    parser = argparse.ArgumentParser(
        prog="q-orca",
        description="Q-Orca — Quantum Orchestrated State Machine Language",
    )
    parser.add_argument("--version", action="version", version=f"q-orca {__version__}")
    parser.add_argument("--stdin", action="store_true", help="Read source from stdin")
    parser.add_argument("--tools", action="store_true", help="Output MCP tool definitions")
    parser.add_argument("--json", action="store_true", help="Output as JSON (use with --tools)")

    sub = parser.add_subparsers(dest="command", required=False)

    # verify
    v = sub.add_parser("verify", help="Parse and verify a quantum machine definition")
    v.add_argument("file", nargs="?", help="Path to .q.orca.md file (or use --stdin)")
    v.add_argument("--json", action="store_true", help="Output as JSON")
    v.add_argument("--skip-completeness", action="store_true", help="Skip stage 2: event completeness checks")
    v.add_argument("--skip-quantum", action="store_true", help="Skip stage 4: quantum-specific checks (unitarity, entanglement)")
    v.add_argument("--skip-dynamic", action="store_true", help="Skip stage 4b: QuTiP circuit simulation (Schmidt rank, entropy)")
    v.add_argument("--skip-resource-bounds", action="store_true", help="Skip stage 4c: resource invariant checks (gate_count, depth, cx_count, t_count, logical_qubits)")
    v.add_argument("--strict", action="store_true", help="Treat warnings as errors (exit 1 on any warning)")
    v.add_argument("--no-follow-imports", action="store_true",
                   help="Do not resolve cross-file `## imports`; non-local invokes report UNRESOLVED_CHILD_MACHINE")
    v.add_argument("--backend", default=None, metavar="BACKEND",
                   help="Verification backend: qutip (default), cuquantum, cudaq")
    v.add_argument("--gpu-count", type=int, default=1, metavar="N",
                   help="Number of GPUs to use (cuquantum backend)")
    v.add_argument("--tensor-network", action="store_true",
                   help="Use tensor-network contraction (cuquantum backend)")

    # compile
    c = sub.add_parser("compile", help="Compile to a target format")
    c.add_argument("format", choices=["mermaid", "qasm", "qiskit", "cudaq"], help="Output format")
    c.add_argument("file", nargs="?", help="Path to .q.orca.md file (or use --stdin)")

    # imports
    im = sub.add_parser("imports", help="Inspect cross-file machine imports")
    im.add_argument("imports_command", choices=["show"], help="imports subcommand")
    im.add_argument("file", nargs="?", help="Path to .q.orca.md file")

    # run
    r = sub.add_parser("run", help="Execute a composed (or single) machine and print its final context")
    r.add_argument("file", nargs="?", help="Path to .q.orca.md file (or use --stdin)")
    r.add_argument("--shots", type=int, default=1024, help="Inner shots for shot-batched quantum children")
    r.add_argument("--seed", type=int, default=None, help="Simulator seed for reproducible runs")
    r.add_argument("--json", action="store_true", help="Output the final context as JSON")

    # simulate
    s = sub.add_parser("simulate", help="Simulate a quantum machine with Qiskit")
    s.add_argument("file", nargs="?", help="Path to .q.orca.md file (or use --stdin)")
    s.add_argument("--run", action="store_true", help="Run simulation immediately")
    s.add_argument("--shots", type=int, default=1024, help="Number of shots for noisy simulation")
    s.add_argument("--analytic", action="store_true", default=False, help="Exact statevector simulation (default: probabilistic via --shots)")
    s.add_argument("--json", action="store_true", help="Output results as JSON")
    s.add_argument("--verbose", action="store_true", help="Include stdout/stderr")
    s.add_argument("--skip-qutip", action="store_true", help="Skip QuTiP verification")
    s.add_argument("--backend", default=None, metavar="BACKEND",
                   help="Simulation backend: qutip (default), cuquantum, cudaq")
    s.add_argument("--gpu-count", type=int, default=1, metavar="N",
                   help="Number of GPUs to use (cuquantum backend)")
    s.add_argument("--tensor-network", action="store_true",
                   help="Use tensor-network contraction (cuquantum backend)")
    s.add_argument("--cudaq-target", default=None, metavar="TARGET",
                   help="CUDA-Q target (e.g. nvidia, qpp-cpu, ionq) — cudaq backend only")
    s.add_argument("--seed", type=int, default=None, metavar="N",
                   help="Seed for shots-based simulation (deterministic counts)")

    args = parser.parse_args()

    # --tools --json for MCP self-description
    if args.tools:
        output = json.dumps(Q_ORCA_TOOLS, indent=2) if args.json else str(Q_ORCA_TOOLS)
        print(output)
        return

    # Resolve source: file path or stdin
    if args.stdin:
        source = sys.stdin.read()
    elif hasattr(args, "file") and args.file:
        source = Path(args.file).read_text()
    else:
        # No source specified and not --tools — show help
        parser.print_help()
        return

    parsed = parse_q_orca_markdown(source)

    if not parsed.file.machines:
        label = args.file if hasattr(args, "file") and args.file else "<stdin>"
        print(f"Error: No machines found in {label}", file=sys.stderr)
        sys.exit(1)

    if args.command == "verify":
        _cmd_verify(parsed, args)
    elif args.command == "compile":
        _cmd_compile(parsed, args)
    elif args.command == "simulate":
        _cmd_simulate(parsed, args)
    elif args.command == "imports":
        _cmd_imports(parsed, args)
    elif args.command == "run":
        _cmd_run(parsed, args)


def _resolve_backend(args, config=None) -> str:
    """Merge CLI --backend flag (priority) over config file value (fallback)."""
    if getattr(args, "backend", None):
        return args.backend
    if config is not None and getattr(config, "backend", None):
        return config.backend
    return "qutip"


def _cmd_verify(parsed, args):
    from q_orca.config.loader import load_config
    try:
        config = load_config()
    except Exception:
        config = None

    backend = _resolve_backend(args, config)

    # Wire gpu_count / tensor_network into cuquantum adapter if selected
    if backend == "cuquantum":
        from q_orca.backends.cuquantum_backend import cuquantum_backend
        cuquantum_backend.gpu_count = getattr(args, "gpu_count", 1)
        cuquantum_backend.tensor_network = getattr(args, "tensor_network", False)

    import_graph = _build_import_graph(parsed, args)

    has_errors = False
    for machine in parsed.file.machines:
        opts = VerifyOptions(
            skip_completeness=args.skip_completeness,
            skip_quantum=args.skip_quantum,
            skip_dynamic=args.skip_dynamic,
            skip_resource_bounds=args.skip_resource_bounds,
            backend=backend,
        )
        result = verify(machine, opts, file=parsed.file, import_graph=import_graph)

        # Collect backend metadata for JSON output
        backend_meta = _get_backend_meta(backend)

        if args.strict:
            warnings_as_errors = [e for e in result.errors if e.severity == "warning"]
            errors_list = [e for e in result.errors if e.severity == "error"]
            result.valid = result.valid and len(warnings_as_errors) == 0
            result.errors = errors_list + warnings_as_errors

        if args.json:
            import json as _json
            print(_json.dumps({
                "machine": machine.name,
                "valid": result.valid,
                "errors": [
                    {"code": e.code, "message": e.message, "severity": e.severity,
                     "suggestion": e.suggestion}
                    for e in result.errors
                ],
                "backend": backend_meta,
            }, indent=2))
        else:
            print(f"\n  Machine: {machine.name}")
            print(f"  States: {', '.join(s.name for s in machine.states)}")
            print(f"  Events: {', '.join(e.name for e in machine.events)}")
            print(f"  Transitions: {len(machine.transitions)}")
            print(f"  Verification rules: {', '.join(r.kind for r in machine.verification_rules)}")
            print("")

            if result.valid:
                print("  Result: VALID")
            else:
                print("  Result: INVALID")
                has_errors = True

            for err in result.errors:
                icon = {"error": "ERR", "warning": "WARN"}.get(err.severity, "INFO")
                print(f"  [{icon}] {err.code}: {err.message}")
                if err.suggestion:
                    print(f"        -> {err.suggestion}")

    sys.exit(1 if has_errors else 0)


def _build_import_graph(parsed, args):
    """Resolve the file's cross-file imports, or None if not applicable."""
    if getattr(args, "no_follow_imports", False):
        return None
    file_path = getattr(args, "file", None)
    if not file_path or not parsed.file.imports:
        return None
    from q_orca.loader.import_resolver import resolve_imports
    return resolve_imports(parsed.file, file_path)


def _cmd_imports(parsed, args):
    from q_orca.compiler.mermaid import compile_import_graph_to_mermaid
    from q_orca.loader.import_resolver import resolve_imports

    file_path = getattr(args, "file", None)
    if not file_path:
        print("Error: `imports show` requires a file path", file=sys.stderr)
        sys.exit(1)
    graph = resolve_imports(parsed.file, file_path)
    print(compile_import_graph_to_mermaid(graph, root_label=Path(file_path).name))


def _cmd_run(parsed, args):
    """Verify, then execute a composed (or single) machine; print final context."""
    import json as _json

    from q_orca.runtime.composed import run_composed
    from q_orca.runtime.types import QIterativeSimulationOptions

    machine = parsed.file.machines[0]
    import_graph = _build_import_graph(parsed, args)

    # Refuse to run a machine that does not verify.
    result = verify(machine, VerifyOptions(skip_dynamic=True), file=parsed.file, import_graph=import_graph)
    if not result.valid:
        print("Error: machine does not verify; refusing to run:", file=sys.stderr)
        for e in result.errors:
            if e.severity == "error":
                print(f"  [ERR] {e.code}: {e.message}", file=sys.stderr)
        sys.exit(1)

    opts = QIterativeSimulationOptions(inner_shots=args.shots, seed_simulator=args.seed)
    base_path = getattr(args, "file", None)
    run_result = run_composed(parsed.file, machine, opts, base_path=base_path, import_graph=import_graph)

    if args.json:
        print(_json.dumps({
            "machine": run_result.machine,
            "final_state": run_result.final_state,
            "final_context": run_result.final_context,
            "child_runs": run_result.child_runs,
        }, indent=2, default=str))
    else:
        print(f"\n  Machine: {run_result.machine}")
        print(f"  Final state: {run_result.final_state}")
        print("  Final context:")
        for k, v in run_result.final_context.items():
            print(f"    {k} = {v}")
        for c in run_result.child_runs:
            shots = c["shots"] if c["shots"] is not None else 1
            print(f"  ↳ invoke {c['invoke_state']} → {c['child']} (shots={shots})")


def _cmd_compile(parsed, args):
    import_graph = _build_import_graph(parsed, args)
    for machine in parsed.file.machines:
        try:
            if args.format == "mermaid":
                print(compile_to_mermaid(machine, file=parsed.file, import_graph=import_graph))
            elif args.format == "qasm":
                print(compile_to_qasm(machine))
            elif args.format == "qiskit":
                opts = QSimulationOptions(analytic=True, run=False)
                print(compile_to_qiskit(machine, opts))
            elif args.format == "cudaq":
                print(compile_to_cudaq(machine))
        except ComposedMachineError as e:
            print(f"  [ERR] {e.code}: {e}")


def _cmd_simulate(parsed, args):
    from q_orca.config.loader import load_config
    try:
        config = load_config()
    except Exception:
        config = None

    backend = _resolve_backend(args, config)

    # Wire gpu_count / tensor_network into cuquantum adapter if selected
    if backend == "cuquantum":
        from q_orca.backends.cuquantum_backend import cuquantum_backend
        cuquantum_backend.gpu_count = getattr(args, "gpu_count", 1)
        cuquantum_backend.tensor_network = getattr(args, "tensor_network", False)

    # Wire cudaq-target into cudaq adapter if selected
    if backend == "cudaq":
        from q_orca.backends.cudaq_backend import cudaq_backend
        cudaq_backend.target = getattr(args, "cudaq_target", None)

    if args.run:
        deps = check_python_dependencies()
        if not deps.python3:
            print("Error: python3 not found. Install Python 3.8+ to run simulations.", file=sys.stderr)
            sys.exit(1)
        if not deps.qiskit:
            print("Error: qiskit not installed. Run: pip install qiskit", file=sys.stderr)
            sys.exit(1)

    options = QSimulationOptions(
        analytic=args.analytic or not args.shots,
        shots=args.shots,
        verbose=args.verbose,
        skip_qutip=args.skip_qutip,
        run=args.run,
        seed_simulator=args.seed,
    )

    backend_meta = _get_backend_meta(backend)

    for machine in parsed.file.machines:
        if args.run:
            result = simulate_machine(machine, options)

            if isinstance(result, QIterativeSimulationResult):
                _print_iterative_result(machine, result, backend_meta, args)
                continue

            if args.json:
                import json as _json
                qutip_dict = None
                if result.qutip_verification:
                    qv = result.qutip_verification
                    qutip_dict = {
                        "unitarityVerified": qv.unitarity_verified,
                        "entanglementVerified": qv.entanglement_verified,
                        "schmidtRank": qv.schmidt_rank,
                        "schmidtNumbers": qv.schmidt_numbers,
                        "purity": qv.purity,
                        "errors": qv.errors,
                    }
                print(_json.dumps({
                    "machine": machine.name,
                    "success": result.success,
                    "probabilities": result.probabilities,
                    "counts": result.counts,
                    "qutipVerification": qutip_dict,
                    "error": result.error,
                    "backend": backend_meta,
                }, indent=2))
            else:
                print(f"\n  Machine: {machine.name}")
                print(f"  Success: {result.success}")
                if result.counts:
                    print(f"  Counts: {result.counts}")
                if result.probabilities:
                    print("  Probabilities:")
                    for state, prob in result.probabilities.items():
                        print(f"    {state}: {prob * 100:.2f}%")
                if result.qutip_verification:
                    qv = result.qutip_verification
                    print("  QuTiP Verification:")
                    print(f"    Unitarity: {'VERIFIED' if qv.unitarity_verified else 'FAILED'}")
                    print(f"    Entanglement: {'VERIFIED' if qv.entanglement_verified else 'FAILED'}")
                    if qv.schmidt_rank is not None:
                        print(f"    Schmidt Rank: {qv.schmidt_rank}")
                if result.error:
                    print(f"  Error: {result.error}")
        else:
            script = compile_to_qiskit(machine, options)
            print(script)


def _print_iterative_result(machine, result, backend_meta, args):
    """Render a QIterativeSimulationResult. Collapsed unless --verbose."""
    if args.json:
        import json as _json

        trace_entries = [
            {
                "iteration": t.iteration,
                "source": t.source_state,
                "target": t.target_state,
                "event": t.event,
                "action": t.action,
                "bits": t.measurement_bits,
                "context": t.context_snapshot,
            }
            for t in (result.trace if args.verbose else [])
        ]
        print(_json.dumps({
            "machine": machine.name,
            "runtime": "iterative",
            "success": result.success,
            "final_state": result.final_state,
            "final_context": result.final_context,
            "aggregate_counts": result.aggregate_counts,
            "iterations": len(result.trace),
            "trace": trace_entries,
            "error": result.error,
            "backend": backend_meta,
        }, indent=2))
        return

    print(f"\n  Machine: {machine.name} (iterative runtime)")
    print(f"  Success: {result.success}")
    if result.final_state:
        print(f"  Final state: {result.final_state}")
    if result.final_context:
        print(f"  Final context: {result.final_context}")
    if result.aggregate_counts:
        print(f"  Aggregate counts: {result.aggregate_counts}")
    print(f"  Iterations: {len(result.trace)}")
    if args.verbose and result.trace:
        print("  Trace:")
        for t in result.trace:
            print(
                f"    [{t.iteration}] {t.source_state} -> {t.target_state} "
                f"event={t.event} action={t.action} bits={t.measurement_bits}"
            )
    if result.error:
        print(f"  Error: {result.error}")


def _get_backend_meta(backend_name: str) -> dict:
    """Return a dict with backend name and version for JSON output."""
    from q_orca.backends import BackendRegistry, BackendUnavailableError
    try:
        adapter = BackendRegistry.get(backend_name)
        return {"name": adapter.name, "version": adapter.version}
    except BackendUnavailableError:
        return {"name": backend_name, "version": "unknown"}


if __name__ == "__main__":
    main()
