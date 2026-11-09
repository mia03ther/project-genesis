"""The GENESIS scenario harness: versioned Web3 learning scenarios.

- ``units``        exact conversion between "1.5 ether" and integer wei
- ``manifest``     the typed scenario schema, its loader and validation
- ``chain``        JSON-RPC client, Anvil adapter and local ``anvil`` process control
- ``environment``  applies, verifies and restores a scenario's initial state (Anvil)
- ``grading``      observations and the deterministic judge
- ``runner``       actors, the run loop and the JSON report
- ``monad``        Monad Testnet adapter: signed transactions via ``cast``,
                   no reset, plus ``genesis monad anchor``
- ``cli``          ``genesis scenario ...`` commands

See ``docs/HARNESS_ARCHITECTURE.md``. Anvil scenarios are local only: no
keys, no public networks, no model calls. Monad scenarios are real public
testnet transactions and need a funded key.
"""
