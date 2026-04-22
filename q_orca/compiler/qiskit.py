"""Q-Orca Qiskit compiler — compiles QMachineDef → Qiskit Python script."""

import re
from dataclasses import dataclass
from typing import Mapping

from q_orca.angle import evaluate_angle
from q_orca.ast import QMachineDef, QuantumGate, QTypeQubit, QTypeScalar, QTypeList, NoiseModel


def _build_angle_context(machine: QMachineDef) -> dict[str, float]:
    """Mirror of `markdown_parser._build_angle_context` for the compiler.

    Kept here so that `_parse_effect_string` can resolve context-field
    angle references identically to the parser, without importing across
    layers.
    """
    out: dict[str, float] = {}
    for f in getattr(machine, "context", []) or []:
        kind = getattr(f.type, "kind", "")
        if kind not in ("int", "float"):
            continue
        if not f.default_value:
            continue
        try:
            out[f.name] = float(f.default_value.strip())
        except (ValueError, AttributeError):
            continue
    return out


def _parse_effect_string(
    effect_str: str,
    angle_context: Mapping[str, float] | None = None,
) -> list[QuantumGate]:
    """Parse an effect string with semicolon-separated gates into a list of QuantumGate."""
    if not effect_str:
        return []
    gates = []
    # Split on semicolons to handle multi-gate effects like "H(qs[0]); H(qs[1])"
    for part in effect_str.split(";"):
        part = part.strip()
        if not part:
            continue
        gate = _parse_single_gate(part, angle_context=angle_context)
        if gate:
            gates.append(gate)
    return gates


def _parse_single_gate(
    effect_str: str,
    angle_context: Mapping[str, float] | None = None,
) -> QuantumGate | None:
    """Parse a single gate from an effect string."""
    effect_str = effect_str.strip()

    # Hadamard(qs[N]) or Hadamard(qs[N] M K)
    m = re.search(r"Hadamard\(\s*(\w+\[(?:\d+(?:\s+\d+)*)?\])\s*\)", effect_str, re.IGNORECASE)
    if m:
        indices_str = m.group(1)
        indices = [int(x) for x in re.findall(r"\d+", indices_str)]
        return QuantumGate(kind="H", targets=indices)

    # CCX / CCNOT / Toffoli / CCZ — two controls + one target (last argument)
    m = re.search(
        r"(CCX|CCNOT|Toffoli|CCZ)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        name = m.group(1).upper()
        c0, c1, tgt = int(m.group(2)), int(m.group(3)), int(m.group(4))
        kind = "CCZ" if name == "CCZ" else "CCNOT"
        return QuantumGate(kind=kind, targets=[tgt], controls=[c0, c1])

    # MCX / MCZ — variable arity, last argument is the target.
    # Requires ≥3 args total (≥2 controls); for 2-control cases use CCX/CCZ.
    m = re.search(
        r"(MCX|MCZ)\(\s*((?:\w+\[\d+\]\s*,\s*){2,}\w+\[\d+\])\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        kind = m.group(1).upper()
        indices = [int(x) for x in re.findall(r"\d+", m.group(2))]
        return QuantumGate(kind=kind, targets=[indices[-1]], controls=indices[:-1])

    # CSWAP / Fredkin — 1 control + 2 swap targets.
    m = re.search(
        r"CSWAP\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*\)",
        effect_str,
        re.IGNORECASE,
    )
    if m:
        ctrl, t1, t2 = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return QuantumGate(kind="CSWAP", targets=[t1, t2], controls=[ctrl])

    # CNOT(qs[control], qs[target]) — also accepts CX alias
    m = re.search(r"(?:CNOT|CX)\(\s*(\w+\[(\d+)\])\s*,\s*(\w+\[(\d+)\])\s*\)", effect_str, re.IGNORECASE)
    if m:
        ctrl = int(m.group(2))
        tgt = int(m.group(4))
        return QuantumGate(kind="CNOT", targets=[tgt], controls=[ctrl])

    # CZ(qs[control], qs[target])
    m = re.search(r"CZ\(\s*(\w+\[(\d+)\])\s*,\s*(\w+\[(\d+)\])\s*\)", effect_str, re.IGNORECASE)
    if m:
        ctrl = int(m.group(2))
        tgt = int(m.group(4))
        return QuantumGate(kind="CZ", targets=[tgt], controls=[ctrl])

    # SWAP(qs[a], qs[b])
    m = re.search(r"SWAP\(\s*(\w+\[(\d+)\])\s*,\s*(\w+\[(\d+)\])\s*\)", effect_str, re.IGNORECASE)
    if m:
        idx1 = int(m.group(2))
        idx2 = int(m.group(4))
        return QuantumGate(kind="SWAP", targets=[idx1, idx2])

    # Two-qubit parameterized gates: CRx/CRy/CRz/RXX/RYY/RZZ(qs[i], qs[j], angle)
    m = re.search(r"(CRx|CRy|CRz|RXX|RYY|RZZ)\(\s*\w+\[(\d+)\]\s*,\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)", effect_str, re.IGNORECASE)
    if m:
        raw_kind = m.group(1).upper()
        canonical_map = {"CRX": "CRx", "CRY": "CRy", "CRZ": "CRz", "RXX": "RXX", "RYY": "RYY", "RZZ": "RZZ"}
        kind = canonical_map.get(raw_kind, raw_kind)
        i = int(m.group(2))
        j = int(m.group(3))
        angle_str = m.group(4).strip()
        try:
            theta = evaluate_angle(angle_str, angle_context)
        except ValueError:
            return None
        if kind in ("CRx", "CRy", "CRz"):
            return QuantumGate(kind=kind, targets=[j], controls=[i], parameter=theta)
        else:
            return QuantumGate(kind=kind, targets=[i, j], parameter=theta)

    # Rx/Ry/Rz(qs[N], <angle>) — canonical qubit-first, angle-second
    m = re.search(r"R([XYZ])\(\s*\w+\[(\d+)\]\s*,\s*([^)]+)\s*\)", effect_str, re.IGNORECASE)
    if m:
        axis = m.group(1).lower()  # canonical GateKind: 'Rx'/'Ry'/'Rz'
        idx = int(m.group(2))
        angle_str = m.group(3).strip()
        try:
            theta = evaluate_angle(angle_str, angle_context)
        except ValueError:
            theta = 0.0  # symbolic parameter — caller should validate upstream
        return QuantumGate(kind=f"R{axis}", targets=[idx], parameter=theta)

    # X(qs[N]), Y(qs[N]), Z(qs[N]), T(qs[N]), S(qs[N])
    m = re.search(r"^([XYZS])\(\s*(\w+\[(\d+)\])\s*\)", effect_str)
    if m:
        kind = m.group(1)
        idx = int(m.group(3))
        return QuantumGate(kind=kind, targets=[idx])

    # Generic single-qubit gate: GateName(qs[N])
    m = re.search(r"^([A-Z][a-zA-Z]*)\(\s*(\w+\[(\d+)\])\s*\)", effect_str)
    if m:
        kind = m.group(1).upper()
        idx = int(m.group(3))
        kind_map = {"H": "H", "X": "X", "Y": "Y", "Z": "Z", "T": "T", "S": "S", "I": "I"}
        if kind in kind_map:
            return QuantumGate(kind=kind_map[kind], targets=[idx])
        return QuantumGate(kind="custom", targets=[idx], custom_name=kind)

    return None


DEFAULT_SHOTS = 1024


def _parse_noise_model_string(text: str) -> NoiseModel | None:
    """Parse a noise model string like 'depolarizing(0.01)' or 'amplitude_damping(0.1)'."""
    if not text:
        return None
    text = text.strip()

    # depolarizing(p)
    m = re.match(r"depolarizing\(\s*([\d.]+)\s*\)", text, re.IGNORECASE)
    if m:
        return NoiseModel(kind="depolarizing", parameter=float(m.group(1)))

    # amplitude_damping(gamma) or amplitudeDamping(gamma)
    m = re.match(r"amplitude[_-]?damping\(\s*([\d.]+)\s*\)", text, re.IGNORECASE)
    if m:
        return NoiseModel(kind="amplitude_damping", parameter=float(m.group(1)))

    # phase_damping(gamma) or phaseDamping(gamma)
    m = re.match(r"phase[_-]?damping\(\s*([\d.]+)\s*\)", text, re.IGNORECASE)
    if m:
        return NoiseModel(kind="phase_damping", parameter=float(m.group(1)))

    # thermal(T1) or thermal(T1, T2) — relaxation times in nanoseconds
    # parameter2=0.0 means T2 defaults to T1 at emission time
    m = re.match(r"thermal\(\s*([\d.]+)(?:\s*,\s*([\d.]+))?\s*\)", text, re.IGNORECASE)
    if m:
        t1 = float(m.group(1))
        t2 = float(m.group(2)) if m.group(2) else 0.0
        return NoiseModel(kind="thermal", parameter=t1, parameter2=t2)

    return None


def _get_noise_models_from_context(machine: QMachineDef) -> list[NoiseModel]:
    """Extract noise models from machine context fields."""
    noise_models = []
    for field in machine.context:
        if field.name == "noise" and isinstance(field.type, QTypeScalar) and field.type.kind == "noise_model":
            if field.default_value:
                nm = _parse_noise_model_string(field.default_value)
                if nm:
                    noise_models.append(nm)
    return noise_models


def _emit_qiskit_noise_model_code(noise_model: NoiseModel, qubit_count: int) -> list[str]:
    """Generate Qiskit noise model code lines."""
    lines = []
    lines.append("# Noise model")
    lines.append("try:")
    lines.append("    from qiskit_aer import noise")
    lines.append("    HAS_AER = True")
    lines.append("except ImportError:")
    lines.append("    HAS_AER = False")
    lines.append("    noise_model = None")
    lines.append("")
    lines.append("if HAS_AER:")

    if noise_model.kind == "depolarizing":
        p = noise_model.parameter
        lines.append(f"    depolarizing_error = noise.depolarizing_error({p}, 1)")
        lines.append("    noise_model = noise.NoiseModel()")
        lines.append("    noise_model.add_all_qubit_quantum_error(depolarizing_error, ['h', 'x', 'y', 'z', 'rx', 'ry', 'rz', 't', 's', 'cnot', 'cx', 'cz', 'swap'])")

    elif noise_model.kind == "amplitude_damping":
        gamma = noise_model.parameter
        lines.append(f"    ad_error = noise.amplitude_damping_error({gamma})")
        lines.append("    noise_model = noise.NoiseModel()")
        lines.append("    noise_model.add_all_qubit_quantum_error(ad_error, ['h', 'x', 'y', 'z', 'rx', 'ry', 'rz', 't', 's', 'cnot', 'cx', 'cz', 'swap'])")

    elif noise_model.kind == "phase_damping":
        gamma = noise_model.parameter
        lines.append(f"    pd_error = noise.phase_damping_error({gamma})")
        lines.append("    noise_model = noise.NoiseModel()")
        lines.append("    noise_model.add_all_qubit_quantum_error(pd_error, ['h', 'x', 'y', 'z', 'rx', 'ry', 'rz', 't', 's', 'cnot', 'cx', 'cz', 'swap'])")

    elif noise_model.kind == "thermal":
        t1 = noise_model.parameter
        t2 = noise_model.parameter2 if noise_model.parameter2 > 0 else t1
        gate_time = 50  # ns — assumed single-qubit gate time
        lines.append(f"    thermal_error = noise.thermal_relaxation_error({t1}, {t2}, {gate_time})")
        lines.append("    noise_model = noise.NoiseModel()")
        lines.append("    # thermal_relaxation_error is a single-qubit channel; applied to single-qubit gates only")
        lines.append("    noise_model.add_all_qubit_quantum_error(thermal_error, ['h', 'x', 'y', 'z', 'rx', 'ry', 'rz', 't', 's'])")

    else:
        lines.append("    noise_model = None")

    return lines


@dataclass
class QSimulationOptions:
    analytic: bool = True
    shots: int = DEFAULT_SHOTS
    verbose: bool = False
    skip_qutip: bool = False
    skip_noise: bool = False
    run: bool = False
    seed_simulator: int | None = None


def compile_to_qiskit(machine: QMachineDef, options: QSimulationOptions) -> str:
    lines = []

    lines.append("# Generated by Q-Orca compiler")
    lines.append(f"# Machine: {machine.name}")
    if any(a.context_update is not None for a in machine.actions):
        lines.append(
            "# NOTE: context-update actions are executed by the iterative "
            "runtime (q_orca.runtime.iterative)."
        )
    lines.append("")

    lines.append("import json")
    lines.append("import sys")
    lines.append("import numpy as np")
    lines.append("")
    lines.append("from qiskit import QuantumCircuit, transpile")
    lines.append("from qiskit.quantum_info import Statevector, Operator")
    lines.append("from qiskit.providers.basic_provider import BasicSimulator")
    lines.append("")

    if not options.skip_qutip:
        lines.append("# QuTiP verification (optional)")
        lines.append("try:")
        lines.append("    import qutip")
        lines.append("    HAS_QUTIP = True")
        lines.append("except ImportError:")
        lines.append("    HAS_QUTIP = False")
        lines.append("")

    qubit_count = _infer_qubit_count(machine)
    bit_count = _infer_bit_count(machine)
    lines.append(f"qubit_count = {qubit_count}")
    if bit_count > 0:
        lines.append(f"bit_count = {bit_count}")
        lines.append(f"qc = QuantumCircuit({qubit_count}, {bit_count})")
    else:
        lines.append(f"qc = QuantumCircuit({qubit_count})")
    lines.append("")

    # Noise model from context
    has_noise_model = False
    if not options.skip_noise:
        noise_models = _get_noise_models_from_context(machine)
        if noise_models:
            for nm in noise_models:
                lines.extend(_emit_qiskit_noise_model_code(nm, qubit_count))
                lines.append("")
                has_noise_model = True

    # Always define HAS_AER (needed by shots branch)
    if not has_noise_model:
        lines.append("# Noise model (none defined in context)")
        lines.append("HAS_AER = False")
        lines.append("noise_model = None")
        lines.append("")

    gate_sequence = _extract_gate_sequence(machine)

    action_map = {a.name: a for a in machine.actions}
    lines.append("# Gate sequence from state machine")
    for action_name, gates, comment in gate_sequence:
        if comment:
            lines.append(f"# {comment}")
        action = action_map.get(action_name)
        if action and action.mid_circuit_measure is not None:
            mcm = action.mid_circuit_measure
            lines.append(f"qc.measure({mcm.qubit_idx}, {mcm.bit_idx})")
        elif action and action.conditional_gate is not None:
            cg = action.conditional_gate
            lines.append(f"with qc.if_test((qc.clbits[{cg.bit_idx}], {cg.value})):")
            lines.append(f"    {_gate_to_qiskit(cg.gate)}")
        elif action and action.context_update is not None:
            raw = action.context_update.raw or action.effect or ""
            lines.append(f"# context_update: {raw}")
        elif gates:
            for gate in gates:
                lines.append(_gate_to_qiskit(gate))

    if options.analytic:
        lines.append("")
        lines.append("# Simulation (analytic)")
        lines.append("sv = Statevector(qc)")
        lines.append("probs = sv.probabilities()")
        lines.append("num_qubits = qc.num_qubits")
        lines.append('bitstrings = [format(i, f"0{num_qubits}b") for i in range(2**num_qubits)]')
        lines.append("prob_dict = dict(zip(bitstrings, probs))")
    else:
        lines.append("")
        lines.append(f"# Simulation ({options.shots} shots)")
        lines.append(f"shots = {options.shots}")
        lines.append("# Add measurements for shots-based simulation")
        lines.append("qc_shots = QuantumCircuit(qubit_count, qubit_count)")
        lines.append("qc_shots.compose(qc, inplace=True)")
        lines.append("for i in range(qubit_count):")
        lines.append("    qc_shots.measure(i, i)")
        lines.append("")
        lines.append("# Decompose multi-controlled / composite gates into the simulator's basis")
        lines.append("_basis = ['h', 'x', 'y', 'z', 's', 'sdg', 't', 'tdg', 'cx', 'cz', 'ccx',")
        lines.append("          'rx', 'ry', 'rz', 'crx', 'cry', 'crz', 'swap', 'measure']")
        lines.append("qc_shots = transpile(qc_shots, basis_gates=_basis)")
        lines.append("")
        seed_kwarg = (
            f", seed_simulator={options.seed_simulator}"
            if options.seed_simulator is not None
            else ""
        )
        lines.append("# Run with noise model if available")
        lines.append("if HAS_AER and noise_model is not None:")
        lines.append("    from qiskit_aer import AerSimulator")
        lines.append("    noisy_backend = AerSimulator(noise_model=noise_model)")
        lines.append(f"    job = noisy_backend.run(qc_shots, shots=shots{seed_kwarg})")
        lines.append("    counts = job.result().get_counts(qc_shots)")
        lines.append("    simulation_method = 'noisy'")
        lines.append("else:")
        lines.append("    backend = BasicSimulator()")
        lines.append(f"    job = backend.run(qc_shots, shots=shots{seed_kwarg})")
        lines.append("    counts = job.result().get_counts(qc_shots)")
        lines.append("    simulation_method = 'ideal'")

    if not options.skip_qutip:
        lines.append("")
        lines.append("# QuTiP Verification")
        lines.append("qutip_result = None")
        lines.append("if HAS_QUTIP:")
        lines.append("    qutip_errors = []")
        lines.append("    unitarity_verified = False")
        lines.append("    entanglement_verified = False")
        lines.append("    schmidt_rank = None")
        lines.append("")
        lines.append("    unitary_matrix = None")
        lines.append("    try:")
        lines.append("        unitary_matrix = Operator(qc).data.tolist()")
        lines.append("    except Exception:")
        lines.append("        qutip_errors.append('Could not extract unitary matrix')")
        lines.append("")
        lines.append("    if unitary_matrix is not None:")
        lines.append("        U = np.array(unitary_matrix)")
        lines.append("        U_dagger = np.conj(U.T)")
        lines.append("        product = np.dot(U, U_dagger)")
        lines.append("        identity = np.eye(len(U))")
        lines.append("        unitarity_error = np.linalg.norm(product - identity)")
        lines.append("        unitarity_verified = bool(unitarity_error < 1e-6)")
        lines.append("        if not unitarity_verified:")
        lines.append("            qutip_errors.append(f'Unitarity error: {unitarity_error}')")
        lines.append("")
        lines.append("    # Compute statevector for Schmidt analysis (use original circuit without measurements)")
        lines.append("    if 'sv' not in dir():")
        lines.append("        try:")
        lines.append("            sv = Statevector(qc)")
        lines.append("        except Exception:")
        lines.append("            sv = None")
        lines.append("")
        lines.append("    try:")
        lines.append("        if sv is not None and len(sv.data) > 0:")
        lines.append("            psi = sv.data.reshape(-1)")
        lines.append("            if len(psi) == 4:")
        lines.append("                psi_2q = psi.reshape(2, 2)")
        lines.append("                s = np.linalg.svd(psi_2q, compute_uv=False)")
        lines.append("                schmidt_rank = int(np.sum(s > 1e-6))")
        lines.append("                entanglement_verified = bool(schmidt_rank > 1)")
        lines.append("    except Exception as e:")
        lines.append("        qutip_errors.append(f'Schmidt analysis failed: {e}')")
        lines.append("")
        lines.append("    qutip_result = {")
        lines.append('        "unitarityVerified": unitarity_verified,')
        lines.append('        "entanglementVerified": entanglement_verified,')
        lines.append("        'schmidtRank': schmidt_rank,")
        lines.append("        'errors': qutip_errors")
        lines.append("    }")
        lines.append("else:")
        lines.append("    qutip_result = {'error': 'QuTiP not installed', 'unitarityVerified': False, 'entanglementVerified': False, 'errors': ['QuTiP not available']}")

    lines.append("")
    lines.append("# Build result")
    lines.append("result = {")
    lines.append(f'    "machine": "{machine.name}",')
    lines.append('    "success": True,')
    lines.append('    "superpositionLeaked": False,')
    lines.append('    "leakDetails": [],')

    if options.analytic:
        lines.append('    "probabilities": prob_dict,')
    else:
        lines.append('    "counts": counts,')

    if not options.skip_qutip:
        lines.append('    "qutipVerification": qutip_result,')

    lines.append("}")
    lines.append("")
    lines.append("print(json.dumps(result, indent=2))")

    return "\n".join(lines)


def _extract_gate_sequence(machine: QMachineDef) -> list:
    """Extract gate sequence from machine, handling multi-gate effects."""
    steps = []
    action_map = {a.name: a for a in machine.actions}
    angle_context = _build_angle_context(machine)

    initial = next((s for s in machine.states if s.is_initial), None)
    if not initial:
        return steps

    visited = set()
    queue = [initial.name]

    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)

        outgoing = [t for t in machine.transitions if t.source == current]

        for t in outgoing:
            if t.action:
                action = action_map.get(t.action)
                if action:
                    # Use effect string to get all gates (not just the first)
                    gates = _parse_effect_string(action.effect, angle_context=angle_context) if action.effect else []
                    # Also fall back to action.gate if effect parsing gave nothing
                    if not gates and action.gate:
                        gates = [action.gate]
                    comment = f"{t.source} --{t.event}--> {t.target}"
                    # Append (action_name, [gates], comment) for each action
                    steps.append((t.action, gates, comment))

            # Stop BFS at terminal (end-of-circuit) measurement events, but
            # continue past mid-circuit measurement events.
            transition_action = action_map.get(t.action) if t.action else None
            is_mid_circuit = (
                transition_action is not None
                and transition_action.mid_circuit_measure is not None
            )
            is_terminal_measure = (
                ("measure" in t.event.lower() or "collapse" in t.event.lower())
                and not is_mid_circuit
            )
            if not is_terminal_measure and t.target not in visited:
                queue.append(t.target)

    return steps


def _gate_to_qiskit(gate: QuantumGate) -> str:
    if gate.kind == "H":
        return f"qc.h({gate.targets[0]})"
    if gate.kind == "X":
        return f"qc.x({gate.targets[0]})"
    if gate.kind == "Y":
        return f"qc.y({gate.targets[0]})"
    if gate.kind == "Z":
        return f"qc.z({gate.targets[0]})"
    if gate.kind == "T":
        return f"qc.t({gate.targets[0]})"
    if gate.kind == "S":
        return f"qc.s({gate.targets[0]})"
    if gate.kind == "CNOT":
        ctrl = gate.controls[0] if gate.controls else 0
        return f"qc.cx({ctrl}, {gate.targets[0]})"
    if gate.kind == "CZ":
        ctrl = gate.controls[0] if gate.controls else 0
        return f"qc.cz({ctrl}, {gate.targets[0]})"
    if gate.kind == "SWAP":
        if len(gate.targets) < 2:
            raise ValueError(f"SWAP gate requires 2 target qubits, got {len(gate.targets)}: {gate.targets}")
        return f"qc.swap({gate.targets[0]}, {gate.targets[1]})"
    if gate.kind == "Rx":
        return f"qc.rx({gate.parameter or 0}, {gate.targets[0]})"
    if gate.kind == "Ry":
        return f"qc.ry({gate.parameter or 0}, {gate.targets[0]})"
    if gate.kind == "Rz":
        return f"qc.rz({gate.parameter or 0}, {gate.targets[0]})"
    if gate.kind == "CRx":
        ctrl = gate.controls[0] if gate.controls else 0
        return f"qc.crx({gate.parameter or 0}, {ctrl}, {gate.targets[0]})"
    if gate.kind == "CRy":
        ctrl = gate.controls[0] if gate.controls else 0
        return f"qc.cry({gate.parameter or 0}, {ctrl}, {gate.targets[0]})"
    if gate.kind == "CRz":
        ctrl = gate.controls[0] if gate.controls else 0
        return f"qc.crz({gate.parameter or 0}, {ctrl}, {gate.targets[0]})"
    if gate.kind == "RXX":
        if len(gate.targets) < 2:
            raise ValueError(f"RXX gate requires 2 target qubits, got {len(gate.targets)}: {gate.targets}")
        return f"qc.rxx({gate.parameter or 0}, {gate.targets[0]}, {gate.targets[1]})"
    if gate.kind == "RYY":
        if len(gate.targets) < 2:
            raise ValueError(f"RYY gate requires 2 target qubits, got {len(gate.targets)}: {gate.targets}")
        return f"qc.ryy({gate.parameter or 0}, {gate.targets[0]}, {gate.targets[1]})"
    if gate.kind == "RZZ":
        if len(gate.targets) < 2:
            raise ValueError(f"RZZ gate requires 2 target qubits, got {len(gate.targets)}: {gate.targets}")
        return f"qc.rzz({gate.parameter or 0}, {gate.targets[0]}, {gate.targets[1]})"
    if gate.kind == "CCNOT":
        ctrls = gate.controls or []
        if len(ctrls) < 2:
            raise ValueError(f"CCNOT gate requires 2 control qubits, got {len(ctrls)}: {ctrls}")
        return f"qc.ccx({ctrls[0]}, {ctrls[1]}, {gate.targets[0]})"
    if gate.kind == "CCZ":
        ctrls = gate.controls or []
        if len(ctrls) < 2:
            raise ValueError(f"CCZ gate requires 2 control qubits, got {len(ctrls)}: {ctrls}")
        # CCZ = H(t) · CCX · H(t); avoids depending on Qiskit's optional ccz alias
        t = gate.targets[0]
        return f"qc.h({t})\nqc.ccx({ctrls[0]}, {ctrls[1]}, {t})\nqc.h({t})"
    if gate.kind == "MCX":
        ctrls = gate.controls or []
        if len(ctrls) < 2:
            raise ValueError(f"MCX gate requires ≥2 control qubits, got {len(ctrls)}: {ctrls}")
        return f"qc.mcx({list(ctrls)}, {gate.targets[0]})"
    if gate.kind == "MCZ":
        ctrls = gate.controls or []
        if len(ctrls) < 2:
            raise ValueError(f"MCZ gate requires ≥2 control qubits, got {len(ctrls)}: {ctrls}")
        # MCZ via H-sandwich on the target → MCX
        t = gate.targets[0]
        return f"qc.h({t})\nqc.mcx({list(ctrls)}, {t})\nqc.h({t})"
    if gate.kind == "CSWAP":
        ctrl = gate.controls[0] if gate.controls else 0
        t1 = gate.targets[1] if len(gate.targets) > 1 else 2
        return f"qc.cswap({ctrl}, {gate.targets[0]}, {t1})"
    if gate.kind == "custom":
        return f"# custom gate: {gate.custom_name or 'unknown'} on qubits {gate.targets}"
    return f"# unknown gate: {gate.kind}"


def _infer_bit_count(machine: QMachineDef) -> int:
    """Count classical bits from list<bit> context fields."""
    for field in machine.context:
        if isinstance(field.type, QTypeList) and field.type.element_type == "bit":
            if field.default_value:
                items = re.findall(r"b\d+", field.default_value)
                if items:
                    return len(items)
            # No default — count from mid_circuit_measure actions
            break
    # Infer bit count from max bit_idx in mid_circuit_measure actions
    max_bit = -1
    for action in machine.actions:
        if action.mid_circuit_measure is not None:
            max_bit = max(max_bit, action.mid_circuit_measure.bit_idx)
        if action.conditional_gate is not None:
            max_bit = max(max_bit, action.conditional_gate.bit_idx)
    return max_bit + 1 if max_bit >= 0 else 0


def build_circuit_for_iteration(
    machine: QMachineDef,
    ctx: Mapping[str, object],
    actions: list,
):
    """Build an in-process `QuantumCircuit` for one iteration segment.

    `actions` is a list of `QActionSignature` objects (in execution order)
    whose effects should be applied on a fresh circuit. Any angle references
    are resolved against `ctx` (the live context snapshot), not the machine's
    static defaults. Mid-circuit and terminal measurements are added in the
    order they appear.

    Raises `ImportError` if qiskit is not installed — callers (the iterative
    runtime) should dependency-check before invoking.
    """
    from qiskit import QuantumCircuit  # local import: runtime-only dep

    n_qubits = _infer_qubit_count(machine)
    n_bits = _infer_bit_count(machine)
    qc = QuantumCircuit(n_qubits, n_bits) if n_bits else QuantumCircuit(n_qubits)

    # Build the angle context once: machine defaults overlaid with the live
    # ctx so unmentioned fields still fall back to the machine declaration.
    angle_ctx: dict[str, float] = dict(_build_angle_context(machine))
    for key, value in ctx.items():
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            angle_ctx[key] = float(value)

    for action in actions:
        # Mid-circuit measurement: qubit N -> bit M.
        if action.mid_circuit_measure is not None:
            m = action.mid_circuit_measure
            qc.measure(m.qubit_idx, m.bit_idx)
            continue

        # Classical feedforward (conditional gate) — rare, left to the
        # existing flat-circuit path; the iterative runtime's per-segment
        # dispatch hands these off as-is.
        if action.conditional_gate is not None:
            cond = action.conditional_gate
            with qc.if_test((qc.clbits[cond.bit_idx], cond.value)):
                _apply_gate_to_circuit(qc, cond.gate)
            continue

        # Regular gate-bearing action: parse effect (live angles) or fall
        # back to the pre-parsed gate.
        gates = (
            _parse_effect_string(action.effect, angle_context=angle_ctx)
            if action.effect
            else []
        )
        if not gates and action.gate:
            gates = [action.gate]
        for gate in gates:
            _apply_gate_to_circuit(qc, gate)

    return qc


def _apply_gate_to_circuit(qc, gate) -> None:
    """Apply a QuantumGate to an in-process QuantumCircuit."""
    kind = gate.kind
    if kind == "H":
        qc.h(gate.targets[0])
        return
    if kind == "X":
        qc.x(gate.targets[0])
        return
    if kind == "Y":
        qc.y(gate.targets[0])
        return
    if kind == "Z":
        qc.z(gate.targets[0])
        return
    if kind == "T":
        qc.t(gate.targets[0])
        return
    if kind == "S":
        qc.s(gate.targets[0])
        return
    if kind == "I":
        qc.id(gate.targets[0])
        return
    if kind == "CNOT":
        ctrl = gate.controls[0] if gate.controls else 0
        qc.cx(ctrl, gate.targets[0])
        return
    if kind == "CZ":
        ctrl = gate.controls[0] if gate.controls else 0
        qc.cz(ctrl, gate.targets[0])
        return
    if kind == "SWAP":
        qc.swap(gate.targets[0], gate.targets[1])
        return
    if kind in ("Rx", "Ry", "Rz"):
        theta = float(gate.parameter or 0.0)
        getattr(qc, kind.lower())(theta, gate.targets[0])
        return
    if kind in ("CRx", "CRy", "CRz"):
        ctrl = gate.controls[0] if gate.controls else 0
        theta = float(gate.parameter or 0.0)
        getattr(qc, f"c{kind[1:].lower()}")(theta, ctrl, gate.targets[0])
        return
    if kind in ("RXX", "RYY", "RZZ"):
        theta = float(gate.parameter or 0.0)
        getattr(qc, kind.lower())(theta, gate.targets[0], gate.targets[1])
        return
    if kind == "CCNOT":
        ctrls = gate.controls or []
        qc.ccx(ctrls[0], ctrls[1], gate.targets[0])
        return
    if kind == "CCZ":
        ctrls = gate.controls or []
        t = gate.targets[0]
        qc.h(t)
        qc.ccx(ctrls[0], ctrls[1], t)
        qc.h(t)
        return
    if kind == "MCX":
        qc.mcx(list(gate.controls or []), gate.targets[0])
        return
    if kind == "MCZ":
        t = gate.targets[0]
        qc.h(t)
        qc.mcx(list(gate.controls or []), t)
        qc.h(t)
        return
    if kind == "CSWAP":
        ctrl = gate.controls[0] if gate.controls else 0
        qc.cswap(ctrl, gate.targets[0], gate.targets[1])
        return
    raise ValueError(f"iterative runtime does not yet support gate kind {kind!r}")


def _infer_qubit_count(machine: QMachineDef) -> int:
    # First, try to infer from context fields
    n_value = None
    has_ancilla = False
    qubits_list_length = None

    for field in machine.context:
        # Check for 'n' int field (commonly used for number of control qubits)
        if field.name == "n" and isinstance(field.type, QTypeScalar) and field.type.kind == "int":
            try:
                n_value = int(field.default_value) if field.default_value else None
            except (ValueError, TypeError):
                n_value = None
        # Check for ancilla qubit field
        if field.name == "ancilla" and isinstance(field.type, QTypeQubit):
            has_ancilla = True
        # Check for explicit qubits list
        if field.name == "qubits" and isinstance(field.type, QTypeList):
            # Try to parse default_value like "[q0, q1, q2]"
            if field.default_value:
                items = re.findall(r"q\d+", field.default_value)
                if items:
                    qubits_list_length = len(items)

    # If we found n control qubits and an ancilla, total is n + 1
    if n_value is not None and has_ancilla:
        return n_value + 1

    # If we found an explicit qubits list, use its length
    if qubits_list_length is not None:
        return qubits_list_length

    # Fall back to parsing state names and expressions for bitstrings
    max_bits = 0
    for state in machine.states:
        m = re.search(r"\|([01]+)>", state.name)
        if m:
            max_bits = max(max_bits, len(m.group(1)))
    for state in machine.states:
        if state.state_expression:
            for m in re.finditer(r"\|([01]+)>", state.state_expression):
                max_bits = max(max_bits, len(m.group(1)))
    for guard in machine.guards:
        if guard.expression.kind == "probability":
            max_bits = max(max_bits, len(guard.expression.outcome.bitstring))

    # Also scan gate targets/controls in actions to catch qubit indices
    max_gate_idx = -1
    for action in machine.actions:
        if action.gate:
            for idx in action.gate.targets or []:
                max_gate_idx = max(max_gate_idx, idx)
            for idx in action.gate.controls or []:
                max_gate_idx = max(max_gate_idx, idx)
        if action.effect:
            for idx_match in re.finditer(r"\w+\[(\d+)\]", action.effect):
                max_gate_idx = max(max_gate_idx, int(idx_match.group(1)))
    if max_gate_idx >= 0:
        max_bits = max(max_bits, max_gate_idx + 1)

    return max_bits or 1
