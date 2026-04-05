"""Q-Orca CLI — command-line interface."""

import argparse
import json
import sys
from pathlib import Path

from q_orca.parser.markdown_parser import parse_q_orca_markdown
from q_orca.verifier import verify, VerifyOptions
from q_orca.compiler.mermaid import compile_to_mermaid
from q_orca.compiler.qasm import compile_to_qasm
from q_orca.compiler.qiskit import compile_to_qiskit, QSimulationOptions
from q_orca.runtime.python import check_python_dependencies, simulate_machine
from q_orca.tools import Q_ORCA_TOOLS


def main():
    parser = argparse.ArgumentParser(
        prog="q-orca",
        description="Q-Orca — Quantum Orchestrated State Machine Language",
    )
    parser.add_argument("--stdin", action="store_true", help="Read source from stdin")
    parser.add_argument("--tools", action="store_true", help="Output MCP tool definitions")
    parser.add_argument("--json", action="store_true", help="Output as JSON (use with --tools)")

    sub = parser.add_subparsers(dest="command", required=False)

    # verify
    v = sub.add_parser("verify", help="Parse and verify a quantum machine definition")
    v.add_argument("file", nargs="?", help="Path to .q.orca.md file (or use --stdin)")
    v.add_argument("--json", action="store_true", help="Output as JSON")
    v.add_argument("--skip-completeness", action="store_true", help="Skip event completeness checks")
    v.add_argument("--skip-quantum", action="store_true", help="Skip quantum-specific checks")
    v.add_argument("--strict", action="store_true", help="Treat warnings as errors (fail on any warning)")

    # compile
    c = sub.add_parser("compile", help="Compile to a target format")
    c.add_argument("format", choices=["mermaid", "qasm", "qiskit"], help="Output format")
    c.add_argument("file", nargs="?", help="Path to .q.orca.md file (or use --stdin)")

    # simulate
    s = sub.add_parser("simulate", help="Simulate a quantum machine with Qiskit")
    s.add_argument("file", nargs="?", help="Path to .q.orca.md file (or use --stdin)")
    s.add_argument("--run", action="store_true", help="Run simulation immediately")
    s.add_argument("--shots", type=int, default=1024, help="Number of shots for noisy simulation")
    s.add_argument("--analytic", action="store_true", default=False, help="Exact statevector simulation (default: probabilistic via --shots)")
    s.add_argument("--json", action="store_true", help="Output results as JSON")
    s.add_argument("--verbose", action="store_true", help="Include stdout/stderr")
    s.add_argument("--skip-qutip", action="store_true", help="Skip QuTiP verification")

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


def _cmd_verify(parsed, args):
    has_errors = False
    for machine in parsed.file.machines:
        opts = VerifyOptions(
            skip_completeness=args.skip_completeness,
            skip_quantum=args.skip_quantum,
        )
        result = verify(machine, opts)

        if args.strict:
            warnings_as_errors = [e for e in result.errors if e.severity == "warning"]
            errors_list = [e for e in result.errors if e.severity == "error"]
            result.valid = result.valid and len(warnings_as_errors) == 0
            result.errors = errors_list + warnings_as_errors

        if args.json:
            import json
            print(json.dumps({
                "machine": machine.name,
                "valid": result.valid,
                "errors": [
                    {"code": e.code, "message": e.message, "severity": e.severity,
                     "suggestion": e.suggestion}
                    for e in result.errors
                ],
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
                icon = "ERR" if err.severity == "error" else "WARN"
                print(f"  [{icon}] {err.code}: {err.message}")
                if err.suggestion:
                    print(f"        -> {err.suggestion}")

    sys.exit(1 if has_errors else 0)


def _cmd_compile(parsed, args):
    for machine in parsed.file.machines:
        if args.format == "mermaid":
            print(compile_to_mermaid(machine))
        elif args.format == "qasm":
            print(compile_to_qasm(machine))
        elif args.format == "qiskit":
            opts = QSimulationOptions(analytic=True, run=False)
            print(compile_to_qiskit(machine, opts))


def _cmd_simulate(parsed, args):
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
    )

    for machine in parsed.file.machines:
        if args.run:
            result = simulate_machine(machine, options)

            if args.json:
                import json
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
                print(json.dumps({
                    "machine": machine.name,
                    "success": result.success,
                    "probabilities": result.probabilities,
                    "counts": result.counts,
                    "qutipVerification": qutip_dict,
                    "error": result.error,
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


if __name__ == "__main__":
    main()
