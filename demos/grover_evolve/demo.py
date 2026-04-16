"""Grover Search variant of the quantum-evolve GA demo.

Evolves a 4-qubit Grover's search state machine (target |1010>, 2 iterations)
using the cuquantum GPU backend for verification.

All GA machinery lives in demos/quantum_evolve/demo.py — this module just
overrides the design goal and backend, then delegates to main() there.

Usage:
    python demos/grover_evolve/demo.py
    python demos/grover_evolve/demo.py --backend qutip --population 5 --generations 4
"""

from __future__ import annotations

import sys
import textwrap
from pathlib import Path

# Make the sibling quantum_evolve package importable
sys.path.insert(0, str(Path(__file__).parent.parent))

import quantum_evolve.demo as _demo  # noqa: E402

# ── Override goal and backend before main() reads the globals ─────────────────

_GROVER_GOAL = textwrap.dedent("""\
    Design a quantum state machine that implements Grover's search algorithm
    on 4 qubits, searching for the target state |1010>.

    Requirements:
    1. Four qubits in context: q0, q1, q2, q3
    2. Initialization phase: apply Hadamard to all 4 qubits to create uniform superposition
    3. Oracle phase: mark the target |1010> by flipping its phase (apply a
       multi-controlled Z (or equivalent CNOT+H decomposition) that introduces
       a -1 phase on |1010> and leaves all other amplitudes unchanged)
    4. Diffusion phase: apply the Grover diffusion operator
       (H^4 · (2|0><0| - I) · H^4) to amplify the target amplitude
    5. Run 2 full Grover iterations (oracle + diffusion each time)
    6. Measurement phase: measure all 4 qubits; the outcome |1010> should have
       high probability (~97%)
    7. Include at least 2 collapse branches in the measurement with probability guards
    8. Mark the post-measurement states as [final]

    State names must be valid identifiers (letters, digits, underscores only —
    no Dirac ket notation in state names).
    Include verification rules: unitarity, entanglement, no_cloning.""")

_demo.DEFAULT_DESIGN_GOAL = _GROVER_GOAL
_demo.DESIGN_GOAL = _GROVER_GOAL
_demo.BACKEND = "cuquantum"

# ── Entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # _parse_args() reads sys.argv so --population, --generations etc. still work
    _demo.asyncio.run(_demo.main())
