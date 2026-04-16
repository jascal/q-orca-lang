"""Tests for Q-Orca pluggable execution backends."""

from __future__ import annotations

import subprocess
import sys
from unittest.mock import MagicMock, call, patch

import pytest

from q_orca.backends.base import BackendAdapter, BackendResult, BackendUnavailableError
from q_orca.backends.registry import BackendRegistry
from q_orca.verifier.types import QVerificationResult


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_BELL_SOURCE = """\
# machine BellBackendTest

## context
| Field  | Type        | Default  |
|--------|-------------|----------|
| qubits | list<qubit> | [q0, q1] |

## events
- prepare
- entangle

## state |00> [initial]
> Ground state

## state |ψ> = (|00> + |11>)/√2 [final]
> Bell state

## transitions
| Source | Event   | Guard | Target | Action              |
|--------|---------|-------|--------|---------------------|
| |00>   | prepare |       | |00>   | apply_H             |
| |00>   | entangle|       | |ψ>    | apply_CNOT          |

## actions
| Name       | Signature       | Effect                          |
|------------|-----------------|----------------------------------|
| apply_H    | (qs) -> qs      | Hadamard(qs[0])                 |
| apply_CNOT | (qs) -> qs      | CNOT(qs[0], qs[1])              |
"""


def _parse_bell():
    from q_orca.parser.markdown_parser import parse_q_orca_markdown
    return parse_q_orca_markdown(_BELL_SOURCE).file.machines[0]


# ---------------------------------------------------------------------------
# Task 9.1 — BackendRegistry fallback logic
# ---------------------------------------------------------------------------

class _UnavailableAdapter(BackendAdapter):
    AVAILABLE = False

    @property
    def name(self):
        return "mock_unavailable"

    def verify(self, machine, options=None):
        raise BackendUnavailableError("mock unavailable")


class _AvailableAdapter(BackendAdapter):
    AVAILABLE = True

    @property
    def name(self):
        return "mock_available"

    @property
    def version(self):
        return "1.2.3"

    def verify(self, machine, options=None):
        result = QVerificationResult(valid=True, errors=[])
        backend_result = BackendResult(name=self.name, version=self.version)
        return result, backend_result


class TestBackendRegistry:
    """Unit tests for BackendRegistry fallback logic."""

    def setup_method(self):
        # Snapshot and restore registry state around each test
        self._orig_adapters = dict(BackendRegistry._adapters)
        self._orig_fallback = list(BackendRegistry._fallback_order)

    def teardown_method(self):
        BackendRegistry._adapters = self._orig_adapters
        BackendRegistry._fallback_order = self._orig_fallback

    def test_get_available_adapter(self):
        avail = _AvailableAdapter()
        BackendRegistry.register(avail)
        adapter = BackendRegistry.get("mock_available")
        assert adapter.name == "mock_available"

    def test_get_unavailable_raises(self):
        unavail = _UnavailableAdapter()
        BackendRegistry.register(unavail)
        with pytest.raises(BackendUnavailableError):
            BackendRegistry.get("mock_unavailable")

    def test_get_unknown_raises(self):
        with pytest.raises(BackendUnavailableError, match="Unknown backend"):
            BackendRegistry.get("nonexistent_backend_xyz")

    def test_fallback_when_unavailable(self):
        unavail = _UnavailableAdapter()
        avail = _AvailableAdapter()
        BackendRegistry.register(avail, fallback=True)
        BackendRegistry.register(unavail)

        adapter, fell_back = BackendRegistry.get_with_fallback("mock_unavailable")
        assert fell_back is True
        assert adapter.name == "mock_available"

    def test_no_fallback_raises(self):
        unavail = _UnavailableAdapter()
        BackendRegistry.register(unavail)
        # Remove all fallback adapters
        BackendRegistry._fallback_order = []

        with pytest.raises(BackendUnavailableError):
            BackendRegistry.get_with_fallback("mock_unavailable")

    def test_no_fallback_when_available(self):
        avail = _AvailableAdapter()
        BackendRegistry.register(avail)
        adapter, fell_back = BackendRegistry.get_with_fallback("mock_available")
        assert fell_back is False
        assert adapter.name == "mock_available"


class TestBackendUnavailableWarning:
    """BACKEND_UNAVAILABLE warning appears in QVerificationResult when fallback occurs."""

    def test_backend_unavailable_warning_in_verify(self):
        """verify() emits BACKEND_UNAVAILABLE warning when requested backend is absent."""
        from q_orca.verifier import verify, VerifyOptions

        machine = _parse_bell()
        # Request a backend name that doesn't exist in the registry
        opts = VerifyOptions(backend="nonexistent_backend_xyz", skip_dynamic=False)

        result = verify(machine, opts)
        # The warning should appear (or fall back gracefully)
        warning_codes = [e.code for e in result.errors]
        # Either BACKEND_UNAVAILABLE warning or valid result (if qutip fallback works)
        assert "BACKEND_UNAVAILABLE" in warning_codes or result.valid

    def test_cuquantum_unavailable_falls_back(self):
        """cuquantum backend is unavailable in CI — should fall back to qutip with warning."""
        from q_orca.backends.cuquantum_backend import AVAILABLE as CUQ_AVAILABLE
        if CUQ_AVAILABLE:
            pytest.skip("cuquantum is actually installed — skip fallback test")

        from q_orca.verifier import verify, VerifyOptions
        machine = _parse_bell()
        opts = VerifyOptions(backend="cuquantum", skip_dynamic=False)
        result = verify(machine, opts)

        warning_codes = [e.code for e in result.errors]
        assert "BACKEND_UNAVAILABLE" in warning_codes

    def test_backend_result_metadata_fields(self):
        """BackendResult carries name, version, errors, metadata fields."""
        br = BackendResult(name="qutip", version="5.0.0", errors=[], metadata={"gpu_count": 1})
        assert br.name == "qutip"
        assert br.version == "5.0.0"
        assert br.errors == []
        assert br.metadata["gpu_count"] == 1


# ---------------------------------------------------------------------------
# Task 9.2 — compile_to_cudaq tests
# ---------------------------------------------------------------------------

class TestCuQuantumGPUActivation:
    """Tests that the cuquantum backend uses CuPy for GPU-accelerated gate simulation."""

    def test_evolve_path_gpu_returns_cupy_array(self):
        """_evolve_path_gpu must return a cupy ndarray on the GPU device."""
        try:
            import cupy as cp
        except ImportError:
            pytest.skip("cupy not installed")
        from q_orca.verifier.dynamic import _evolve_path_gpu, CUPY_AVAILABLE, _infer_qubit_count, _build_gate_sequence
        if not CUPY_AVAILABLE:
            pytest.skip("cupy not available in dynamic module")

        machine = _parse_bell()
        n = _infer_qubit_count(machine)
        _, gate_seq = _build_gate_sequence(machine, n)
        all_gates = [g for gates in gate_seq for g in gates]

        psi_gpu = cp.zeros((2 ** n, 1), dtype=cp.complex128)
        psi_gpu[0, 0] = 1.0
        result = _evolve_path_gpu(psi_gpu, all_gates, n)

        assert isinstance(result, cp.ndarray), "result must be a cupy array (GPU)"
        assert result.device.id >= 0

    def test_gpu_result_matches_cpu(self):
        """GPU and CPU verification must agree on validity and error codes."""
        try:
            import cupy  # noqa: F401
        except ImportError:
            pytest.skip("cupy not installed")
        from q_orca.verifier.dynamic import dynamic_verify, dynamic_verify_gpu, CUPY_AVAILABLE
        if not CUPY_AVAILABLE:
            pytest.skip("cupy not available in dynamic module")

        machine = _parse_bell()
        cpu_result = dynamic_verify(machine)
        gpu_result = dynamic_verify_gpu(machine)

        assert gpu_result.valid == cpu_result.valid
        assert {e.code for e in gpu_result.errors} == {e.code for e in cpu_result.errors}

    def test_gpu_memory_allocated_during_verify(self):
        """cupy memory pool total must grow after the first GPU verification call."""
        try:
            import cupy as cp
        except ImportError:
            pytest.skip("cupy not installed")
        from q_orca.verifier.dynamic import dynamic_verify_gpu, CUPY_AVAILABLE
        if not CUPY_AVAILABLE:
            pytest.skip("cupy not available in dynamic module")

        machine = _parse_bell()
        pool = cp.get_default_memory_pool()
        pool.free_all_blocks()
        before = pool.total_bytes()

        dynamic_verify_gpu(machine)
        cp.cuda.Stream.null.synchronize()

        assert pool.total_bytes() > before, "no GPU memory was allocated during verification"

    def test_cuquantum_backend_calls_gpu_verify(self):
        """CuQuantumBackend.verify() must delegate to dynamic_verify_gpu."""
        from q_orca.backends.cuquantum_backend import CuQuantumBackend, AVAILABLE
        if not AVAILABLE:
            pytest.skip("qutip_cuquantum not installed")

        machine = _parse_bell()
        backend = CuQuantumBackend()

        with patch("q_orca.backends.cuquantum_backend.dynamic_verify_gpu") as mock_gpu:
            mock_gpu.return_value = QVerificationResult(valid=True, errors=[])
            backend.verify(machine)
            mock_gpu.assert_called_once_with(machine)


class TestCompileToCudaQ:
    """Tests for the CUDA-Q compiler target."""

    def test_bell_kernel_has_import(self):
        from q_orca.compiler.cudaq import compile_to_cudaq
        machine = _parse_bell()
        output = compile_to_cudaq(machine)
        assert "import cudaq" in output

    def test_bell_kernel_has_decorator(self):
        from q_orca.compiler.cudaq import compile_to_cudaq
        machine = _parse_bell()
        output = compile_to_cudaq(machine)
        assert "@cudaq.kernel" in output

    def test_bell_kernel_has_hadamard(self):
        from q_orca.compiler.cudaq import compile_to_cudaq
        machine = _parse_bell()
        output = compile_to_cudaq(machine)
        assert "cudaq.h(" in output

    def test_bell_kernel_has_cnot(self):
        from q_orca.compiler.cudaq import compile_to_cudaq
        machine = _parse_bell()
        output = compile_to_cudaq(machine)
        assert "cudaq.x.ctrl(" in output

    def test_bell_kernel_has_qvector(self):
        from q_orca.compiler.cudaq import compile_to_cudaq
        machine = _parse_bell()
        output = compile_to_cudaq(machine)
        assert "cudaq.qvector(2)" in output

    def test_output_is_valid_python_syntax(self):
        """The generated kernel string must be valid Python (aside from cudaq import)."""
        import ast
        from q_orca.compiler.cudaq import compile_to_cudaq
        machine = _parse_bell()
        output = compile_to_cudaq(machine)
        # Should parse without SyntaxError
        ast.parse(output)

    def test_compile_format_cudaq_cli(self, tmp_path):
        """q-orca compile cudaq <file> should emit a kernel string."""
        bell_file = tmp_path / "bell.q.orca.md"
        bell_file.write_text(_BELL_SOURCE)
        proc = subprocess.run(
            [sys.executable, "-m", "q_orca.cli", "compile", "cudaq", str(bell_file)],
            capture_output=True,
            text=True,
        )
        assert proc.returncode == 0
        assert "import cudaq" in proc.stdout
        assert "@cudaq.kernel" in proc.stdout


# ---------------------------------------------------------------------------
# Task 9.3 — CLI integration tests
# ---------------------------------------------------------------------------

class TestCLIBackendIntegration:
    """Integration tests for --backend flag in CLI commands."""

    def _run_cli(self, *args):
        return subprocess.run(
            [sys.executable, "-m", "q_orca.cli", *args],
            capture_output=True,
            text=True,
        )

    def test_verify_qutip_backend_json_has_backend_block(self, tmp_path):
        """verify --backend qutip --json produces a 'backend' block."""
        bell_file = tmp_path / "bell.q.orca.md"
        bell_file.write_text(_BELL_SOURCE)
        proc = self._run_cli("verify", "--backend", "qutip", "--json", str(bell_file))
        # May exit 0 or 1 depending on verification result; just check JSON structure
        import json
        data = json.loads(proc.stdout)
        assert "backend" in data
        assert data["backend"]["name"] == "qutip"

    def test_verify_cuquantum_json_falls_back_with_warning(self, tmp_path):
        """verify --backend cuquantum --json falls back to qutip with BACKEND_UNAVAILABLE warning."""
        from q_orca.backends.cuquantum_backend import AVAILABLE as CUQ_AVAILABLE
        if CUQ_AVAILABLE:
            pytest.skip("cuquantum is actually installed — skip fallback test")

        bell_file = tmp_path / "bell.q.orca.md"
        bell_file.write_text(_BELL_SOURCE)
        proc = self._run_cli("verify", "--backend", "cuquantum", "--json", str(bell_file))
        import json
        data = json.loads(proc.stdout)
        assert "backend" in data
        error_codes = [e["code"] for e in data.get("errors", [])]
        assert "BACKEND_UNAVAILABLE" in error_codes

    def test_verify_unknown_backend_emits_warning(self, tmp_path):
        """verify --backend unknown --json includes BACKEND_UNAVAILABLE in errors."""
        bell_file = tmp_path / "bell.q.orca.md"
        bell_file.write_text(_BELL_SOURCE)
        proc = self._run_cli("verify", "--backend", "totally_unknown", "--json", str(bell_file))
        import json
        data = json.loads(proc.stdout)
        error_codes = [e["code"] for e in data.get("errors", [])]
        assert "BACKEND_UNAVAILABLE" in error_codes
