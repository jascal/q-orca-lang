# machine QuantumExperimentController

## context
| Field          | Type   | Default |
|----------------|--------|---------|
| experiment     | string | ""      |
| iteration      | int    | 0       |
| max_iterations | int    | 3       |
| error_count    | int    | 0       |
| status         | string | "idle"  |

## events
- START_EXPERIMENT
- DESIGN_COMPLETE
- VERIFICATION_PASSED
- VERIFICATION_FAILED
- REFINEMENT_COMPLETE
- COMPILE_COMPLETE
- ANALYSIS_COMPLETE

## state idle [initial]
> Waiting for quantum experiment specification

## state designing
> Generating quantum circuit from specification

## state verifying
> Running Q-Orca 5-stage verification pipeline

## state refining
> Refining quantum circuit to fix verification errors

## state compiling
> Compiling verified circuit to QASM and Qiskit

## state analyzing
> Analyzing compilation output and circuit properties

## state complete [final]
> Experiment pipeline complete

## state failed [final]
> Experiment failed after max refinement retries

## transitions
| Source    | Event               | Guard     | Target    | Action            |
|-----------|---------------------|-----------|-----------|-------------------|
| idle      | START_EXPERIMENT    |           | designing | init_experiment   |
| designing | DESIGN_COMPLETE     |           | verifying | verify_circuit    |
| verifying | VERIFICATION_PASSED |           | compiling | compile_circuit   |
| verifying | VERIFICATION_FAILED | can_retry | refining  | refine_circuit    |
| verifying | VERIFICATION_FAILED | !can_retry| failed    | log_failure       |
| refining  | REFINEMENT_COMPLETE |           | verifying | verify_circuit    |
| compiling | COMPILE_COMPLETE    |           | analyzing | analyze_results   |
| analyzing | ANALYSIS_COMPLETE   |           | complete  | log_success       |

## guards
| Name      | Expression                             |
|-----------|----------------------------------------|
| can_retry | ctx.iteration < ctx.max_iterations     |

## actions
| Name             | Signature            |
|------------------|----------------------|
| init_experiment  | (ctx) -> Context     |
| verify_circuit   | (ctx) -> Context     |
| compile_circuit  | (ctx) -> Context     |
| refine_circuit   | (ctx) -> Context     |
| analyze_results  | (ctx) -> Context     |
| log_failure      | (ctx) -> Context     |
| log_success      | (ctx) -> Context     |
