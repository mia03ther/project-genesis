"""Applies a scenario's initial state to a local chain, verifies it, and restores it.

The environment is the only code that changes chain state outside the actor's
submission. Its contract is simple: after :meth:`ScenarioEnvironment.initialize`
and after every :meth:`ScenarioEnvironment.reset`, the chain is in exactly the
state the manifest describes, and that has been checked, not assumed.
"""

from __future__ import annotations

from dataclasses import dataclass

from genesis.harness.chain import AnvilChain, ChainError
from genesis.harness.manifest import ScenarioManifest
from genesis.models import GenesisError


class ScenarioSetupError(GenesisError):
    """The chain could not be brought into, or back to, the scenario's initial state."""


@dataclass(frozen=True, slots=True)
class AccountState:
    label: str
    address: str
    balance: int
    nonce: int


class ScenarioEnvironment:
    def __init__(self, chain: AnvilChain, manifest: ScenarioManifest) -> None:
        self.chain = chain
        self.manifest = manifest
        self.client_version: str | None = None
        self._snapshot: str | None = None

    @property
    def initialized(self) -> bool:
        return self._snapshot is not None

    def initialize(self) -> dict[str, AccountState]:
        """Fund and impersonate every scenario account, verify, and snapshot the chain."""
        self.client_version = self.chain.require_anvil()
        chain_id = self.chain.chain_id()
        if chain_id != self.manifest.environment.chain_id:
            raise ScenarioSetupError(
                f"the chain has id {chain_id}, but scenario {self.manifest.scenario.id!r} "
                f"expects {self.manifest.environment.chain_id}"
            )
        for account in self.manifest.accounts:
            self.chain.set_balance(account.address, account.balance)
            self.chain.impersonate(account.address)
        self._require_initial_state("initialization")
        self._snapshot = self.chain.snapshot()
        return self.state()

    def state(self) -> dict[str, AccountState]:
        """Current balance and nonce of every scenario account, by label."""
        return {
            account.label: AccountState(
                account.label,
                account.address,
                self.chain.balance(account.address),
                self.chain.nonce(account.address),
            )
            for account in self.manifest.accounts
        }

    def verify(self) -> list[str]:
        """Differences between the chain and the manifest's initial state (empty when equal)."""
        problems: list[str] = []
        for account in self.manifest.accounts:
            balance = self.chain.balance(account.address)
            if balance != account.balance:
                problems.append(f"{account.label}: balance is {balance} wei, expected {account.balance}")
            nonce = self.chain.nonce(account.address)
            if nonce != 0:
                problems.append(f"{account.label}: nonce is {nonce}, expected 0 (a fresh account)")
            if self.chain.code(account.address) not in ("0x", "0x0", ""):
                problems.append(f"{account.label}: has contract code, expected a plain account")
        return problems

    def reset(self) -> None:
        """Restore the snapshot taken at initialization and verify the result.

        Anvil discards a snapshot when it is reverted to, so a fresh one is
        taken straight away; the environment can be reset any number of times.
        """
        if self._snapshot is None:
            raise ScenarioSetupError("the environment has not been initialized")
        try:
            reverted = self.chain.revert(self._snapshot)
        except ChainError as error:
            raise ScenarioSetupError(f"evm_revert failed: {error}") from error
        if not reverted:
            raise ScenarioSetupError(f"the chain no longer has snapshot {self._snapshot}")
        self._snapshot = self.chain.snapshot()
        self._require_initial_state("reset")

    def _require_initial_state(self, when: str) -> None:
        problems = self.verify()
        if problems:
            raise ScenarioSetupError(f"the initial state is wrong after {when}: {'; '.join(problems)}")
