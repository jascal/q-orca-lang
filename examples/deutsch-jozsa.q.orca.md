# machine DeutschJozsa

## context
| Field       | Type          | Default   |
|-------------|---------------|-----------|
| qubits      | list<qubit>   | [q0, q1] |
| is_constant | bool          | false     |

## events
- prepare
- apply_oracle
- measure_result

## state |01>
> Initial state: input qubit |0>, output qubit |1>

## state |+-> = (|0>+|1>)(|0>-|1>)/2
> After Hadamard on both qubits

## state |oracle_applied>
> After oracle U_f applied

## state |constant> [final]
> Oracle is constant (f(0)=f(1))

## state |balanced> [final]
> Oracle is balanced (f(0)≠f(1))

## transitions
| Source            | Event          | Guard                  | Target            | Action          |
|-------------------|----------------|------------------------|-------------------|-----------------|
| |01>              | prepare        |                        | |+->              | apply_H_both    |
| |+->              | apply_oracle   |                        | |oracle_applied>  | apply_U_f       |
| |oracle_applied>  | measure_result | measure_q0_is_0        | |constant>        | mark_constant   |
| |oracle_applied>  | measure_result | !measure_q0_is_0       | |balanced>        | mark_balanced   |

## guards
| Name              | Expression         |
|-------------------|--------------------|
| measure_q0_is_0   | ctx.outcome == 0   |

## actions
| Name           | Signature         | Effect           |
|----------------|-------------------|------------------|
| apply_H_both   | (qs) -> qs        | Hadamard(qs[0])  |
| apply_U_f      | (qs) -> qs        | oracle_query     |
| mark_constant  | (ctx) -> ctx      | ctx.is_constant = true |
| mark_balanced  | (ctx) -> ctx      | ctx.is_constant = false |

## effects
| Name          | Input          | Output          |
|---------------|----------------|-----------------|
| oracle_query  | superposition  | phase-kicked    |

## verification rules
- unitarity: all gates preserve norm
- completeness: both constant and balanced outcomes reachable
- no-cloning: no copy ops allowed
