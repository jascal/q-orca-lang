# machine VQEH

## context
| Field         | Type          | Default |
|---------------|---------------|---------|
| qubits        | list<qubit>   | [q0, q1] |
| theta         | float         | 0.0    |
| energy        | float         | 0.0    |
| iteration     | int           | 0      |

## events
- init
- apply_ansatz
- eval_energy
- update_theta
- check_convergence

## state |start>
> Initial state |00>

## state |ψ_ansatz> = Ry(θ)⊗Ry(θ)|00> then CNOT|00>
> Ansatz state: entangled parameterized state

## state |measured>
> Energy ⟨XX + YY + ZZ⟩/4 measured

## state |updated>
> Classical gradient descent step

## state |converged> [final]
> |energy| < 0.05 or iteration >= 20

## state |not_converged>
> Energy above threshold, iterations remain

## transitions
| Source          | Event             | Guard            | Target            | Action               |
|-----------------|-------------------|-----------------|-------------------|----------------------|
| |start>        | init              |                 | |ψ_ansatz>        | apply_ansatz         |
| |start>        | apply_ansatz      |                 | |start>            |                     |
| |start>        | eval_energy       |                 | |start>            |                     |
| |start>        | update_theta      |                 | |start>            |                     |
| |start>        | check_convergence |                 | |start>            |                     |
| |ψ_ansatz>     | init              |                 | |ψ_ansatz>          |                     |
| |ψ_ansatz>     | apply_ansatz      |                 | |ψ_ansatz>          | apply_ansatz         |
| |ψ_ansatz>     | eval_energy       |                 | |measured>          |                     |
| |ψ_ansatz>     | update_theta      |                 | |ψ_ansatz>          |                     |
| |ψ_ansatz>     | check_convergence |                 | |ψ_ansatz>          |                     |
| |measured>     | init              |                 | |measured>           |                     |
| |measured>     | apply_ansatz      |                 | |measured>           |                     |
| |measured>     | eval_energy       |                 | |measured>           |                     |
| |measured>     | update_theta      |                 | |updated>           | set_energy           |
| |measured>     | check_convergence | energy_ok        | |converged>          |                     |
| |measured>     | check_convergence | !energy_ok        | |not_converged>      |                     |
| |updated>      | init              |                 | |updated>            |                     |
| |updated>      | apply_ansatz      |                 | |updated>            |                     |
| |updated>      | eval_energy       |                 | |updated>            |                     |
| |updated>      | update_theta      | iter_max         | |converged>          | increment_iter       |
| |updated>      | update_theta      | !iter_max        | |ψ_ansatz>           | increment_iter       |
| |updated>      | check_convergence |                 | |updated>            |                     |
| |converged>    | init              |                 | |converged>          |                     |
| |converged>    | apply_ansatz      |                 | |converged>          |                     |
| |converged>    | eval_energy       |                 | |converged>          |                     |
| |converged>    | update_theta      |                 | |converged>          |                     |
| |converged>    | check_convergence |                 | |converged>          |                     |
| |not_converged>| init              |                 | |not_converged>      |                     |
| |not_converged>| apply_ansatz      |                 | |not_converged>      |                     |
| |not_converged>| eval_energy       |                 | |not_converged>      |                     |
| |not_converged>| update_theta      | iter_max         | |converged>          | increment_iter       |
| |not_converged>| update_theta      | !iter_max        | |ψ_ansatz>           | increment_iter       |
| |not_converged>| check_convergence | energy_ok        | |converged>          |                     |
| |not_converged>| check_convergence | !energy_ok        | |not_converged>      |                     |

## guards
| Name           | Expression        |
|----------------|-------------------|
| energy_ok      | abs(energy) < 0.05 |
| iter_max       | iteration >= 20    |

## actions
| Name            | Signature             | Effect                            |
|-----------------|-----------------------|----------------------------------|
| apply_ansatz    | (qs, theta) -> qs   | Ry(qs[0], theta); Ry(qs[1], theta); CNOT(qs[0], qs[1]) |
| set_energy      | (ctx) -> ctx          | ctx.energy = ctx.theta * ctx.theta - 1.0 |
| increment_iter  | (ctx) -> ctx          | ctx.iteration = ctx.iteration + 1 |

## effects
| Name          | Input                    | Output              |
|---------------|--------------------------|---------------------|
| ansatz_prep   | parameterized angle θ     | entangled state     |
| energy_eval   | entangled ansatz state   | energy estimate      |

## verification rules
- unitarity: all gates preserve norm
- completeness: all branches converge or continue iterating
- no-cloning: no copy operations
