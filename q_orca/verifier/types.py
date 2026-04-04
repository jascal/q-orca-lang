"""Q-Orca verification types."""

from dataclasses import dataclass, field
from typing import Optional

from q_orca.ast import QMachineDef, QStateDef, QTransition


Severity = str  # 'error' | 'warning'


@dataclass
class QVerificationError:
    code: str
    message: str
    severity: Severity
    location: Optional[dict] = None
    suggestion: Optional[str] = None


@dataclass
class QVerificationResult:
    valid: bool
    errors: list[QVerificationError]


@dataclass
class QStateInfo:
    state: QStateDef
    incoming: list[QTransition] = field(default_factory=list)
    outgoing: list[QTransition] = field(default_factory=list)
    events_handled: set = field(default_factory=set)


@dataclass
class QMachineAnalysis:
    machine: QMachineDef
    state_map: dict
    initial_state: Optional[QStateDef]
    final_states: list[QStateDef]
    orphan_events: list[str]
    orphan_actions: list[str]
    orphan_effects: list[str]
