"""Qubit-role lookups (add-qubit-role-types).

Roles are stored index-aligned on `QMachineDef.qubit_roles` (declaration order),
parsed from the `## context` `list<qubit>` default. These helpers are the shared
read path for the verifier rules and the noise-model `qs[role:R]` selector.
"""

from __future__ import annotations

from q_orca.ast import DEFAULT_QUBIT_ROLE, QMachineDef


def role_of(machine: QMachineDef, index: int) -> str:
    """Role of the qubit at `index` (declaration order); `data` if unknown."""
    roles = machine.qubit_roles
    if 0 <= index < len(roles):
        return roles[index]
    return DEFAULT_QUBIT_ROLE


def qubits_with_role(machine: QMachineDef, role: str) -> list[int]:
    """Indices of every qubit whose declared role is `role`."""
    return [i for i, r in enumerate(machine.qubit_roles) if r == role]


def has_nondefault_roles(machine: QMachineDef) -> bool:
    """True if the machine declares any role other than the `data` default."""
    return any(r != DEFAULT_QUBIT_ROLE for r in machine.qubit_roles)
