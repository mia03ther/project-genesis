"""The GENESIS scenario harness: versioned Web3 learning scenarios on a local chain.

- ``units``        exact conversion between "1.5 ether" and integer wei
- ``manifest``     the typed scenario schema, its loader and validation
- ``chain``        JSON-RPC client, Anvil adapter and local ``anvil`` process control
- ``environment``  applies, verifies and restores a scenario's initial state
- ``grading``      observations and the deterministic judge
- ``runner``       actors, the run loop and the JSON report
- ``cli``          ``genesis scenario ...`` commands

See ``docs/HARNESS_ARCHITECTURE.md``. Phase 1 is local only: no keys, no public
networks, no model calls.
"""
