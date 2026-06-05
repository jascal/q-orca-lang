"""QEC decoding and the logical-error-rate benchmark (add-stabilizer-decoder).

`decode_logical_error_rate(circuit, …)` is the generic decoder: given a
`stim.Circuit` carrying `DETECTOR` / `OBSERVABLE_INCLUDE` annotations and noise,
it builds the detector error model, constructs a PyMatching minimum-weight
perfect-matching decoder from it, samples the detector syndrome + the true
logical observable, decodes each shot, and returns the logical error rate (the
fraction whose decoded observable-flip prediction disagrees with the truth).

`logical_error_rate(machine, …)` is the machine-level wrapper: compile the
machine to its detector circuit, then decode. The decode step is engine-agnostic
— it works on any Stim circuit, so it is validated against Stim's own generated
QEC circuits independently of the q-orca→Stim translation.
"""

from __future__ import annotations

from typing import Optional

PYMATCHING_AVAILABLE = False
try:
    import pymatching as _pymatching  # noqa: F401
    PYMATCHING_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised only without pymatching
    pass


class DecoderUnavailableError(RuntimeError):
    """Raised when the MWPM decoder dependency (PyMatching) is not installed."""


def _require_decoder() -> None:
    if not PYMATCHING_AVAILABLE:
        raise DecoderUnavailableError(
            "decoder unavailable — install the matching decoder with "
            "`pip install 'q-orca[stabilizer]'` (provides pymatching)"
        )


def decode_logical_error_rate(circuit, shots: int, seed: Optional[int] = None) -> float:
    """Logical error rate of a detector-annotated `stim.Circuit` under MWPM.

    Builds the detector error model, decodes each shot's detector syndrome with
    PyMatching, and returns the fraction of shots whose predicted logical-flip
    disagrees with the sampled observable. Seeded for reproducibility.
    """
    _require_decoder()
    import pymatching

    dem = circuit.detector_error_model(decompose_errors=True)
    matching = pymatching.Matching.from_detector_error_model(dem)
    detectors, observables = circuit.compile_detector_sampler(seed=seed).sample(
        shots, separate_observables=True
    )
    predictions = matching.decode_batch(detectors)
    # A shot is a logical error when the decoder's predicted observable flip
    # disagrees with the actually-sampled observable (any observable column).
    return float((predictions != observables).any(axis=1).mean())


def logical_error_rate(machine, shots: int, seed: Optional[int] = None) -> float:
    """Compile a Clifford QEC machine to its detector circuit and decode it.

    Requires a machine with `ancilla`/`syndrome` role tags and a `## noise_model`
    (without noise the syndrome is trivially zero — nothing to decode).
    """
    from q_orca.compiler.stabilizer import compile_to_stim_with_detectors

    return decode_logical_error_rate(compile_to_stim_with_detectors(machine), shots, seed)
