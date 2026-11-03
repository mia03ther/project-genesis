# GENESIS scenario harness: architecture (Phase 1)

Phase 1 lays the foundation for Web3 learning scenarios: a versioned scenario
format, a loader that validates it, an adapter for a local development chain,
a deterministic judge, and one complete scenario, *First Local Blockchain
Transfer*. It deliberately contains no AI agents, no model calls, no public
networks and no security challenges. Those come later, on top of the pieces
described here.

## Four things that are easy to confuse

| | What it is | What it is not | In GENESIS |
| --- | --- | --- | --- |
| **Agent harness** | The code that drives an *actor*: it presents the task and observations, exposes the only actions the actor may take, turns the actor's output into those actions, enforces budgets, and records what happened. | It does not decide whether the result is correct. | The `Actor` interface in [`runner.py`](../genesis/harness/runner.py). Phase 1 has one actor, the scripted *reference actor*. A learner interface or a model adapter (Claude, GPT, Gemini) would be other actors behind the same interface. |
| **Execution sandbox** | The environment where actions take effect, with a known initial state and limits on what can be touched. It has two separate properties: *reproducibility* (known start, clean reset) and *isolation* (containing untrusted code). | Reproducibility is not isolation. An ordinary process or container that resets cleanly can still be escaped by hostile code. | A local Anvil chain bound to `127.0.0.1` with synthetic accounts ([`chain.py`](../genesis/harness/chain.py), [`environment.py`](../genesis/harness/environment.py)). It gives reproducible, disposable *chain state*. It is **not** an isolation boundary, and Phase 1 runs no untrusted code at all. |
| **Benchmark dataset** | A versioned collection of task definitions: initial conditions, the expected outcome, and grading rules. Data, not code. | It does not run anything. | Scenario manifests under [`scenarios/`](../scenarios), each with its own version, in the format of [SCENARIO_FORMAT.md](SCENARIO_FORMAT.md). |
| **Evaluation harness** | The machinery that runs a task: it validates the definition, prepares the environment, asks the actor for its action, observes the result, grades it deterministically, writes a report, and resets. | It is not the actor and not the environment; it orchestrates both. | The scenario runner, the judge ([`grading.py`](../genesis/harness/grading.py)) and the JSON report. |

The separation matters for the learning platform: a person working through a
scenario and, later, an AI agent being evaluated on it are both *actors* on the
same scenario, judged by the same rules, so their results are comparable. The
existing civilization simulation follows the same principle: agents only
propose, and the engine validates and records.

## Components

```text
 scenarios/<id>/scenario.toml        benchmark dataset: versioned manifests
            |
            v
 manifest.py   load + validate ----> invalid manifests fail with every error listed
            |
            v
 runner.py     ScenarioRunner (evaluation harness)
   1. start or attach a local chain        chain.py       AnvilProcess, AnvilChain (127.0.0.1 only)
   2. apply initial state, verify, snapshot environment.py ScenarioEnvironment
   3. ask the actor for a submission       runner.py      Actor (reference actor in Phase 1)
   4. validate and execute the submission
   5. observe receipt, transaction, balances and nonces
   6. judge                                 grading.py     deterministic criteria
   7. report                                runner.py      JSON report with a normalized digest
   8. reset: revert to the snapshot and verify the initial state again
```

| Module | Responsibility |
| --- | --- |
| `units.py` | Exact conversion between `"1.5 ether"`, gwei and integer wei |
| `manifest.py` | Typed, immutable scenario schema; TOML/JSON loader; validation that reports every problem with its location; manifest digest |
| `chain.py` | Minimal JSON-RPC client (standard library only), a typed adapter for the Anvil methods the harness uses, and a controller for a local `anvil` process |
| `environment.py` | Applies a manifest's initial accounts, verifies them, snapshots the chain and restores it |
| `grading.py` | The observation record, the criteria checks and the deterministic judge, with no chain access |
| `runner.py` | Actors, submission validation, the run loop, repeat runs and the report |
| `cli.py` | `genesis scenario list / validate / run` |

## Lifecycle and reset

1. The runner starts its own `anvil` process on a free loopback port (or
   attaches to one given by `--rpc-url`, which must be a loopback address and
   must report itself as Anvil).
2. The environment checks the chain id, gives every scenario account its exact
   starting balance with `anvil_setBalance`, enables `anvil_impersonateAccount`
   for it, verifies balances, nonces (0) and the absence of contract code, and
   takes an `evm_snapshot`.
3. The actor returns a submission; the runner checks that it only refers to
   scenario accounts and sane values before sending it with
   `eth_sendTransaction`.
4. After grading, `evm_revert` restores the snapshot. Anvil discards a snapshot
   when it is reverted to, so the environment immediately takes a new one, and
   then re-verifies the initial state. Every run therefore starts from the same
   conditions, and `--repeat N` checks that repeated runs agree.

**No private keys exist anywhere.** Scenario accounts are synthetic addresses
(for example `0x…a11ce`) whose transactions Anvil accepts through
impersonation. Nothing in Phase 1 signs anything.

## Determinism and normalization

The grading of a run is deterministic: the judge is a pure function of the
manifest and the observation. The observation, however, mixes values that are
fixed by the rules of the scenario with values that depend on the node:

| Deterministic for a given manifest | Environment-specific (recorded, never compared) |
| --- | --- |
| chain id, sender, recipient, value | transaction hash and block hash |
| receipt status | block number and timestamp |
| gas used by a plain transfer (21,000 on current Ethereum rules) | gas price and therefore the fee amount |
| balances before the run | node client and version |
| balance changes once the fee is accounted for | transaction type and fee fields |
| nonce changes, grading results | |

Transaction hashes depend on fields such as gas price and the (impersonated)
signature, and block hashes on timestamps, so identical hashes are **not**
claimed, not even between two runs on the same machine. The report instead
contains a *normalized observation* built only from the left-hand column and
its SHA-256 digest. Repeated runs of the same scenario must produce the same
normalized digest, and the integration test checks exactly that.

What was actually observed, on Anvil 1.8.7 under Windows 11: three runs in
one session, with a reset between them, all landed in block 1 at an effective
gas price of 2 gwei and produced *identical* transaction and block hashes.
This is an observation for that version and timing, not a guarantee. The
normalized digest was identical on Anvil and on the in-repository test double,
which uses a gas price of 1 gwei; a pinned test checks that value on both.

## Anvil-local versus Monad Testnet

Everything in Phase 1 is Anvil-local and has been verified on Anvil 1.8.7
only. Nothing has been run against Monad Testnet and no compatibility is
claimed.

| | Anvil (implemented, Phase 1) | Monad Testnet (future, separate adapter) |
| --- | --- | --- |
| Where | a process on this machine, `127.0.0.1` | a public test network reached over the internet |
| Accounts | synthetic addresses, impersonated, no keys | real key pairs; every transaction must be signed |
| Funds | set directly with `anvil_setBalance` | test tokens from a faucet; cannot be set |
| Reset | `evm_snapshot` / `evm_revert` | impossible; history is permanent and public |
| Determinism | fresh, private chain per run | shared state, other users, variable latency |
| Gas and fees | Anvil's local EVM rules | Monad's own fee rules, which may differ and must be verified with tests |

A Monad integration will therefore be a separate adapter with its own key
handling, funding, confirmation and normalization rules and its own tests. It
will never be a flag on the Anvil adapter. Scenarios declare their environment
(`environment.kind`), so a scenario that can only run locally can never be sent
to a public network by accident.

## Extension points

- **Actors.** `Actor.submit(task) -> Submission` is the only way an action
  enters a run. A learner interface and model adapters for Claude, GPT and
  Gemini are future implementations; the runner validates whatever they
  return, exactly as the simulation engine validates its agents' proposals.
- **Chain adapters.** The environment talks to the chain only through
  `AnvilChain`'s small set of methods. Another network gets its own adapter.
- **Checks.** New criteria are added to the judge's registry with their own
  tests; unknown checks are rejected when a manifest is loaded.
- **Scenario kinds.** Phase 1 supports one kind of task, a single value
  transfer. New kinds, such as contract interaction, come with a new
  `manifest_version`.

## Scope and safety of Phase 1

- Local only: the adapter refuses non-loopback RPC URLs and nodes that do not
  identify as Anvil, and binds the `anvil` process it starts to `127.0.0.1`.
- Synthetic assets only: test ether that exists on a throwaway local chain.
- No untrusted code is executed. When later phases run code written by
  learners or agents, that code will need a real isolation boundary, such as a
  separate virtual machine. Neither the Anvil process nor an ordinary Docker
  container is sufficient on its own.
- No model calls, no paid API keys, no wallets, no public transactions, and no
  token contracts.
