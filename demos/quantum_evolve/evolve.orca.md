# machine QuantumEvolver

## context
| Field           | Type   | Default |
|-----------------|--------|---------|
| generation      | int    | 0       |
| max_generations | int    | 3       |
| best_fitness    | float  | 0.0     |
| fitness_target  | float  | 80.0    |
| population_size | int    | 0       |
| status          | string | "idle"  |

## events
- START
- POPULATION_READY
- EVALUATION_DONE
- SELECTION_DONE
- BREEDING_DONE

## state idle [initial]
> Waiting for design goal specification

## state initializing
> Generating initial population of quantum machines via LLM

## state evaluating
> Scoring each individual's fitness against the design goal

## state selecting
> Tournament selection of parents for breeding

## state breeding
> LLM-assisted crossover and mutation to produce next generation

## state converged [final]
> A machine met the fitness target

## state exhausted [final]
> Max generations reached without convergence

## transitions
| Source       | Event            | Guard           | Target       | Action            |
|--------------|------------------|-----------------|--------------|-------------------|
| idle         | START            |                 | initializing | init_population   |
| initializing | POPULATION_READY |                 | evaluating   | evaluate_fitness  |
| evaluating   | EVALUATION_DONE  | has_converged   | converged    | report_best       |
| evaluating   | EVALUATION_DONE  | has_generations | selecting    | select_parents    |
| evaluating   | EVALUATION_DONE  | !has_generations| exhausted    | report_best       |
| selecting    | SELECTION_DONE   |                 | breeding     | breed_next_gen    |
| breeding     | BREEDING_DONE    |                 | evaluating   | evaluate_fitness  |

## guards
| Name            | Expression                              |
|-----------------|-----------------------------------------|
| has_converged   | ctx.best_fitness >= ctx.fitness_target   |
| has_generations | ctx.generation < ctx.max_generations    |

## actions
| Name             | Signature        |
|------------------|------------------|
| init_population  | (ctx) -> Context |
| evaluate_fitness | (ctx) -> Context |
| select_parents   | (ctx) -> Context |
| breed_next_gen   | (ctx) -> Context |
| report_best      | (ctx) -> Context |
