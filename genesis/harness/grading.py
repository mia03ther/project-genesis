"""Observations of a run and the deterministic judge.

:func:`grade` is a pure function of a manifest and an observation. It never
talks to a chain, reads a clock or draws a random number, so the same inputs
always produce the same grade. Each check named in ``manifest.CHECKS`` has
exactly one evaluator here.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import asdict, dataclass
from typing import Any

from genesis.harness.manifest import CHECKS, Criterion, ScenarioManifest
from genesis.harness.units import describe_wei

#: Fields of an observation that depend on the node and are recorded but never compared.
ENVIRONMENT_SPECIFIC_FIELDS = (
    "transaction_hash",
    "block_hash",
    "block_number",
    "effective_gas_price_wei",
    "fee_wei",
    "transaction_type",
    "client_version",
)


@dataclass(frozen=True, slots=True)
class TransferObservation:
    """What happened on chain after one submission, as recorded by the runner.

    Balances and nonces are keyed by account label and cover every scenario account.
    """

    chain_id: int
    client_version: str
    tx_hash: str
    tx_from: str
    tx_to: str | None
    tx_value: int
    tx_nonce: int
    tx_gas_limit: int
    tx_type: int | None
    status: int
    gas_used: int
    effective_gas_price: int
    block_number: int
    block_hash: str
    balances_before: Mapping[str, int]
    balances_after: Mapping[str, int]
    nonces_before: Mapping[str, int]
    nonces_after: Mapping[str, int]

    @property
    def fee(self) -> int:
        """Wei paid for gas: gas used x effective gas price."""
        return self.gas_used * self.effective_gas_price

    def normalized(self, manifest: ScenarioManifest) -> dict[str, Any]:
        """The part of the observation that is fixed by the scenario, not by the node.

        Balance changes are reported with the fee added back for the account
        that paid it, so they do not depend on the node's gas price.
        """
        payer = manifest.label_of(self.tx_from)
        changes: dict[str, str] = {}
        for label, before in sorted(self.balances_before.items()):
            change = self.balances_after[label] - before + (self.fee if label == payer else 0)
            changes[label] = str(change)
        return {
            "chain_id": self.chain_id,
            "from": payer or self.tx_from,
            "to": manifest.label_of(self.tx_to) or self.tx_to,
            "value_wei": str(self.tx_value),
            "status": self.status,
            "gas_used": self.gas_used,
            "balances_before_wei": {
                label: str(value) for label, value in sorted(self.balances_before.items())
            },
            "balance_changes_excluding_fee_wei": changes,
            "nonce_changes": {
                label: self.nonces_after[label] - before
                for label, before in sorted(self.nonces_before.items())
            },
        }

    def environment_specific(self) -> dict[str, Any]:
        """Values that depend on the node and its configuration (see ``ENVIRONMENT_SPECIFIC_FIELDS``)."""
        return {
            "transaction_hash": self.tx_hash,
            "block_hash": self.block_hash,
            "block_number": self.block_number,
            "effective_gas_price_wei": str(self.effective_gas_price),
            "fee_wei": str(self.fee),
            "transaction_type": self.tx_type,
            "client_version": self.client_version,
        }


def digest(value: Any) -> str:
    """SHA-256 of canonical JSON (sorted keys, no whitespace)."""
    payload = json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


@dataclass(frozen=True, slots=True)
class CriterionResult:
    id: str
    check: str
    description: str
    required: bool
    points: int
    awarded: int
    passed: bool
    expected: str
    actual: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class GradeResult:
    criteria: tuple[CriterionResult, ...]
    score: int
    max_score: int
    pass_threshold: int

    @property
    def failed_required(self) -> tuple[str, ...]:
        return tuple(result.id for result in self.criteria if result.required and not result.passed)

    @property
    def passed(self) -> bool:
        """At least ``pass_threshold`` points and no failed required criterion."""
        return self.score >= self.pass_threshold and not self.failed_required

    def to_dict(self) -> dict[str, Any]:
        return {
            "passed": self.passed,
            "score": self.score,
            "max_score": self.max_score,
            "pass_threshold": self.pass_threshold,
            "failed_required": list(self.failed_required),
            "criteria": [result.to_dict() for result in self.criteria],
        }


Evaluator = Callable[[ScenarioManifest, Criterion, TransferObservation], tuple[bool, str, str]]


def _who(manifest: ScenarioManifest, address: str | None) -> str:
    if address is None:
        return "no recipient (contract creation)"
    label = manifest.label_of(address)
    return f"{address.lower()} ({label})" if label else f"{address.lower()} (not a scenario account)"


def _expect_int(criterion: Criterion) -> int:
    if not isinstance(criterion.expect, int):
        raise TypeError(f"criterion {criterion.id!r} needs an integer 'expect'")
    return criterion.expect


def _account(criterion: Criterion) -> str:
    if criterion.account is None:
        raise TypeError(f"criterion {criterion.id!r} needs an 'account'")
    return criterion.account


def _receipt_status(
    manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation
) -> tuple[bool, str, str]:
    expected = 1 if criterion.expect == "success" else 0
    actual = "success" if obs.status == 1 else "reverted"
    return obs.status == expected, f"{criterion.expect} ({expected})", f"{actual} ({obs.status})"


def _sender(
    manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation
) -> tuple[bool, str, str]:
    expected = manifest.account(manifest.transaction.sender).address
    return obs.tx_from.lower() == expected, _who(manifest, expected), _who(manifest, obs.tx_from)


def _recipient(
    manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation
) -> tuple[bool, str, str]:
    expected = manifest.account(manifest.transaction.recipient).address
    actual = obs.tx_to.lower() if obs.tx_to else None
    return actual == expected, _who(manifest, expected), _who(manifest, obs.tx_to)


def _value(
    manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation
) -> tuple[bool, str, str]:
    expected = manifest.transaction.value
    return obs.tx_value == expected, describe_wei(expected), describe_wei(obs.tx_value)


def _final_balance(
    manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation
) -> tuple[bool, str, str]:
    label, expected = _account(criterion), _expect_int(criterion)
    actual = obs.balances_after[label]
    return actual == expected, f"{label}: {describe_wei(expected)}", f"{label}: {describe_wei(actual)}"


def _sender_pays(
    manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation
) -> tuple[bool, str, str]:
    label = manifest.transaction.sender
    drop = obs.balances_before[label] - obs.balances_after[label]
    expected = obs.tx_value + obs.fee
    detail = f"value {obs.tx_value} + fee {obs.gas_used} gas x {obs.effective_gas_price} wei"
    return drop == expected, f"{label} pays {expected} wei ({detail})", f"{label} paid {drop} wei"


def _gas_used(
    manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation
) -> tuple[bool, str, str]:
    expected = _expect_int(criterion)
    return obs.gas_used == expected, f"{expected} gas", f"{obs.gas_used} gas"


def _nonce_increment(
    manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation
) -> tuple[bool, str, str]:
    label, expected = _account(criterion), _expect_int(criterion)
    change = obs.nonces_after[label] - obs.nonces_before[label]
    return change == expected, f"{label}: +{expected}", f"{label}: {change:+d}"


EVALUATORS: Mapping[str, Evaluator] = {
    "receipt_status": _receipt_status,
    "sender": _sender,
    "recipient": _recipient,
    "value": _value,
    "final_balance": _final_balance,
    "sender_pays_value_and_fee": _sender_pays,
    "gas_used": _gas_used,
    "nonce_increment": _nonce_increment,
}
if set(EVALUATORS) != set(CHECKS):  # pragma: no cover - a programming error caught at import
    raise RuntimeError("every check in the manifest vocabulary needs exactly one evaluator")


def grade(manifest: ScenarioManifest, observation: TransferObservation) -> GradeResult:
    """Apply every criterion of the manifest to the observation, in manifest order."""
    results = []
    for criterion in manifest.grading.criteria:
        passed, expected, actual = EVALUATORS[criterion.check](manifest, criterion, observation)
        results.append(
            CriterionResult(
                id=criterion.id,
                check=criterion.check,
                description=criterion.description,
                required=criterion.required,
                points=criterion.points,
                awarded=criterion.points if passed else 0,
                passed=passed,
                expected=expected,
                actual=actual,
            )
        )
    return GradeResult(
        criteria=tuple(results),
        score=sum(result.awarded for result in results),
        max_score=manifest.grading.max_score,
        pass_threshold=manifest.grading.pass_threshold,
    )
