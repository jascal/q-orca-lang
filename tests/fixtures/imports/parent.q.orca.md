# machine BellConsumer

> Imports the PrepareBellPair primitive from a library file and invokes it.

## context
| Field     | Type | Default |
|-----------|------|---------|
| iteration | int  | 0       |

## imports
| Path                      | Aliases         |
|---------------------------|-----------------|
| ./lib/bell-pair.q.orca.md | PrepareBellPair |

## events
- advance

## state |idle> [initial]
## state |prep> [invoke: PrepareBellPair(seed=iteration)]
## state |done> [final]

## transitions
| Source | Event   | Guard | Target | Action |
|--------|---------|-------|--------|--------|
| |idle> | advance |       | |prep> |        |
| |prep> | advance |       | |done> |        |
