# Contributing to Q-Orca

We welcome contributions of all kinds — new examples, language features, verification rules, hardware backends, and research integrations.

## Good First Issues

- **New example machines** — add a `.q.orca.md` file to `examples/` for any quantum algorithm (Simon's, QPE, QAOA variants, BB84, etc.)
- **Noise model improvements** — extend the `## context noise` field to support new Qiskit Aer channels
- **Verifier rules** — add new checks to the 5-stage pipeline (e.g. resource estimation, T-gate count)
- **Documentation** — improve docstrings, add type hints, or expand the spec in `docs/specs/`

## Development Setup

```bash
git clone https://github.com/jascal/q-orca-lang
cd q-orca-lang
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[all]"
pytest  # all tests should pass
```

## Adding a New Example

1. Create `examples/your-algorithm.q.orca.md`
2. Run `q-orca verify examples/your-algorithm.q.orca.md --strict`
3. Add a row to the examples table in `README.md`
4. Open a PR — CI will verify it passes across Python 3.10–3.13

## Adding a Verifier Rule

1. Add your check function to the appropriate module in `q_orca/verifier/`
2. Register it in `q_orca/verifier/__init__.py`
3. Write tests in `tests/test_verifier.py`
4. Document the new error code in `docs/specs/`

## Research Directions

See [`docs/specs/`](docs/specs/) for planned features. Open problems we'd love help on:

- Equivalence checking between two quantum machines (quantum process fidelity)
- Quantum automata language power analysis
- Hardware backend targeting (IBM Quantum, IonQ, Rigetti)
- Density matrix / mixed state support
- GPU-accelerated verification via NVIDIA cuQuantum

## Questions?

Open an issue — we're friendly and responsive.
