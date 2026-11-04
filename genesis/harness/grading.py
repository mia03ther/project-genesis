"""Observations of a run and the deterministic judge.

:func:`grade` (version 1 scenarios) and :func:`grade_variant` (version 2) are
pure functions of a manifest and an observation. They never talk to a chain,
read a clock or draw a random number, so the same inputs always produce the
same grade. Each check named in ``manifest.CHECKS`` has exactly one evaluator
here, and every result carries an explanation written for a learner.
"""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any, NamedTuple

from genesis.harness.authorization import describe_difference
from genesis.harness.manifest import CHECKS, Criterion, ScenarioManifest
from genesis.harness.units import describe_wei, format_wei

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

DECISIONS = ("accepted", "rejected")


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
            "balances_before_wei": {label: str(value) for label, value in sorted(self.balances_before.items())},
            "balance_changes_excluding_fee_wei": changes,
            "nonce_changes": {
                label: self.nonces_after[label] - before for label, before in sorted(self.nonces_before.items())
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


@dataclass(frozen=True, slots=True)
class VariantObservation:
    """Everything the judge sees about one run of one variant.

    ``decision`` is what the validator decided about the variant's request.
    ``transfer`` is the executed transaction, or ``None`` when nothing was
    sent. Balances and nonces before and after are always recorded, so a
    refusal can be shown, and checked, to have left the chain untouched.
    """

    variant: str
    decision: str
    reasons: tuple[str, ...]
    chain_id: int
    transfer: TransferObservation | None
    balances_before: Mapping[str, int]
    balances_after: Mapping[str, int]
    nonces_before: Mapping[str, int]
    nonces_after: Mapping[str, int]

    @classmethod
    def from_transfer(cls, observation: TransferObservation) -> VariantObservation:
        """Wrap the single transfer of a version 1 run."""
        return cls(
            variant="",
            decision="accepted",
            reasons=(),
            chain_id=observation.chain_id,
            transfer=observation,
            balances_before=observation.balances_before,
            balances_after=observation.balances_after,
            nonces_before=observation.nonces_before,
            nonces_after=observation.nonces_after,
        )

    def balance_changes(self) -> dict[str, int]:
        return {label: self.balances_after[label] - before for label, before in self.balances_before.items()}

    def normalized(self, manifest: ScenarioManifest) -> dict[str, Any]:
        """The deterministic part, as for :meth:`TransferObservation.normalized`."""
        payer = manifest.label_of(self.transfer.tx_from) if self.transfer is not None else None
        fee = self.transfer.fee if self.transfer is not None else 0
        return {
            "variant": self.variant,
            "decision": self.decision,
            "transfer": self.transfer.normalized(manifest) if self.transfer is not None else None,
            "balances_before_wei": {label: str(value) for label, value in sorted(self.balances_before.items())},
            "balance_changes_excluding_fee_wei": {
                label: str(change + (fee if label == payer else 0))
                for label, change in sorted(self.balance_changes().items())
            },
            "nonce_changes": {
                label: self.nonces_after[label] - before for label, before in sorted(self.nonces_before.items())
            },
        }

    def environment_specific(self) -> dict[str, Any] | None:
        return self.transfer.environment_specific() if self.transfer is not None else None


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
    #: Why the check passed or failed, in plain language.
    explanation: str = ""

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


class CheckOutcome(NamedTuple):
    passed: bool
    expected: str
    actual: str
    explanation: str


Evaluator = Callable[[ScenarioManifest, Criterion, VariantObservation], CheckOutcome]
TransferEvaluator = Callable[[ScenarioManifest, Criterion, TransferObservation], CheckOutcome]


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


def _needs_transfer(evaluate: TransferEvaluator) -> Evaluator:
    """Adapt a check of the executed transaction to runs where nothing may have been sent."""

    def check(manifest: ScenarioManifest, criterion: Criterion, observation: VariantObservation) -> CheckOutcome:
        if observation.transfer is None:
            return CheckOutcome(
                False,
                "a sent transaction",
                "no transaction was sent",
                "This check needs a transaction, but the request was refused, so nothing was sent.",
            )
        return evaluate(manifest, criterion, observation.transfer)

    return check


def _receipt_status(manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation) -> CheckOutcome:
    expected = 1 if criterion.expect == "success" else 0
    actual = "success" if obs.status == 1 else "reverted"
    passed = obs.status == expected
    if obs.status == 1:
        explanation = "The receipt status is 1: the transaction was executed and its effects are on chain."
    else:
        explanation = "The receipt status is 0: the transaction reverted, so only the gas fee was paid."
    return CheckOutcome(passed, f"{criterion.expect} ({expected})", f"{actual} ({obs.status})", explanation)


def _sender(manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation) -> CheckOutcome:
    label = manifest.transaction.sender
    expected = manifest.account(label).address
    passed = obs.tx_from.lower() == expected
    explanation = (
        f"The transaction was sent from {label}'s address."
        if passed
        else f"The transaction was sent from {obs.tx_from.lower()}, not from {label}."
    )
    return CheckOutcome(passed, _who(manifest, expected), _who(manifest, obs.tx_from), explanation)


def _recipient(manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation) -> CheckOutcome:
    label = manifest.transaction.recipient
    expected = manifest.account(label).address
    actual = obs.tx_to.lower() if obs.tx_to else None
    passed = actual == expected
    if passed:
        explanation = f"The transaction paid {label}, the expected recipient."
    elif actual is None:
        explanation = "The transaction had no recipient at all."
    else:
        explanation = f"The transaction paid {actual}, not {label}. " + describe_difference(expected, actual)
    return CheckOutcome(passed, _who(manifest, expected), _who(manifest, obs.tx_to), explanation)


def _value(manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation) -> CheckOutcome:
    expected = manifest.transaction.value
    passed = obs.tx_value == expected
    explanation = (
        f"Exactly {format_wei(expected)} was sent."
        if passed
        else f"{format_wei(obs.tx_value)} was sent instead of {format_wei(expected)}."
    )
    return CheckOutcome(passed, describe_wei(expected), describe_wei(obs.tx_value), explanation)


def _final_balance(manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation) -> CheckOutcome:
    label, expected = _account(criterion), _expect_int(criterion)
    actual = obs.balances_after[label]
    passed = actual == expected
    explanation = (
        f"{label} ends with exactly {format_wei(expected)}."
        if passed
        else f"{label} ends with {format_wei(actual)} instead of {format_wei(expected)}."
    )
    return CheckOutcome(passed, f"{label}: {describe_wei(expected)}", f"{label}: {describe_wei(actual)}", explanation)


def _sender_pays(manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation) -> CheckOutcome:
    label = manifest.transaction.sender
    drop = obs.balances_before[label] - obs.balances_after[label]
    expected = obs.tx_value + obs.fee
    detail = f"value {obs.tx_value} + fee {obs.gas_used} gas x {obs.effective_gas_price} wei"
    passed = drop == expected
    explanation = (
        f"{label} paid the value plus a fee of {obs.gas_used} gas x {obs.effective_gas_price} wei, to the wei."
        if passed
        else f"{label}'s balance fell by {drop} wei, but value plus fee comes to {expected} wei."
    )
    return CheckOutcome(passed, f"{label} pays {expected} wei ({detail})", f"{label} paid {drop} wei", explanation)


def _gas_used(manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation) -> CheckOutcome:
    expected = _expect_int(criterion)
    passed = obs.gas_used == expected
    explanation = (
        f"The transaction used exactly {expected:,} gas."
        if passed
        else f"The transaction used {obs.gas_used:,} gas instead of {expected:,}."
    )
    return CheckOutcome(passed, f"{expected} gas", f"{obs.gas_used} gas", explanation)


def _nonce_increment(manifest: ScenarioManifest, criterion: Criterion, obs: TransferObservation) -> CheckOutcome:
    label, expected = _account(criterion), _expect_int(criterion)
    change = obs.nonces_after[label] - obs.nonces_before[label]
    passed = change == expected
    explanation = (
        f"{label}'s nonce rose by {expected}: every transaction from an account uses up one nonce."
        if passed
        else f"{label}'s nonce changed by {change} instead of {expected}."
    )
    return CheckOutcome(passed, f"{label}: +{expected}", f"{label}: {change:+d}", explanation)


def _decision(manifest: ScenarioManifest, criterion: Criterion, obs: VariantObservation) -> CheckOutcome:
    variant = manifest.variant(obs.variant)
    expected = "accepted" if variant.expect == "accept" else "rejected"
    passed = obs.decision == expected
    if passed and expected == "accepted":
        explanation = "This request matches the authorization, so paying it was correct."
    elif passed:
        explanation = "This request does not match the authorization, so refusing it was correct."
    elif expected == "rejected":
        explanation = "This request does not match the authorization and should have been refused, but it was paid."
    else:
        explanation = "This request matches the authorization and should have been paid, but it was refused."
    return CheckOutcome(passed, expected, obs.decision, explanation)


def _authorized_transfer(manifest: ScenarioManifest, criterion: Criterion, obs: VariantObservation) -> CheckOutcome:
    authorization = manifest.authorization
    if authorization is None:  # excluded by manifest validation
        raise TypeError("authorized_transfer needs a version 2 manifest")
    payer = manifest.account(authorization.payer).address
    recipient = manifest.account(authorization.recipient).address
    expected = (
        f"{format_wei(authorization.value)} from {authorization.payer} to "
        f"{authorization.recipient} ({recipient}) on chain {authorization.chain_id}, or nothing at all"
    )
    transfer = obs.transfer
    if transfer is None:
        return CheckOutcome(True, expected, "no transfer", "No transfer was executed, so nothing unauthorized was paid.")
    paid_to = (transfer.tx_to or "").lower()
    actual = (
        f"{format_wei(transfer.tx_value)} from {_who(manifest, transfer.tx_from)} to "
        f"{_who(manifest, transfer.tx_to)} on chain {transfer.chain_id}"
    )
    problems = []
    if transfer.tx_from.lower() != payer:
        problems.append(f"it was paid by {transfer.tx_from.lower()} instead of {authorization.payer}")
    if paid_to != recipient:
        problems.append(
            f"it paid {paid_to} instead of {authorization.recipient}. " + describe_difference(recipient, paid_to)
        )
    if transfer.tx_value != authorization.value:
        problems.append(f"it moved {format_wei(transfer.tx_value)} instead of {format_wei(authorization.value)}")
    if transfer.chain_id != authorization.chain_id:
        problems.append(f"it ran on chain {transfer.chain_id} instead of {authorization.chain_id}")
    if not problems:
        explanation = "The executed transfer matches the authorization: payer, recipient, value and chain."
        return CheckOutcome(True, expected, actual, explanation)
    explanation = "The executed transfer broke the authorization: " + "; ".join(problems)
    return CheckOutcome(False, expected, actual, explanation)


def _balances_unchanged(manifest: ScenarioManifest, criterion: Criterion, obs: VariantObservation) -> CheckOutcome:
    changes = [
        f"{label} {'+' if change > 0 else ''}{format_wei(change)}"
        for label, change in sorted(obs.balance_changes().items())
        if change
    ]
    nonce_changes = [
        f"{label} nonce {obs.nonces_after[label] - before:+d}"
        for label, before in sorted(obs.nonces_before.items())
        if obs.nonces_after[label] != before
    ]
    moved = changes + nonce_changes
    if not moved:
        explanation = "No balance or nonce changed: nothing was signed or sent."
        return CheckOutcome(True, "no change", "no change", explanation)
    return CheckOutcome(False, "no change", "; ".join(moved), "The chain changed: " + "; ".join(moved) + ".")


EVALUATORS: Mapping[str, Evaluator] = {
    "receipt_status": _needs_transfer(_receipt_status),
    "sender": _needs_transfer(_sender),
    "recipient": _needs_transfer(_recipient),
    "value": _needs_transfer(_value),
    "final_balance": _needs_transfer(_final_balance),
    "sender_pays_value_and_fee": _needs_transfer(_sender_pays),
    "gas_used": _needs_transfer(_gas_used),
    "nonce_increment": _needs_transfer(_nonce_increment),
    "decision": _decision,
    "authorized_transfer": _authorized_transfer,
    "balances_unchanged": _balances_unchanged,
}
if set(EVALUATORS) != set(CHECKS):  # pragma: no cover - a programming error caught at import
    raise RuntimeError("every check in the manifest vocabulary needs exactly one evaluator")


def _grade(manifest: ScenarioManifest, criteria: Sequence[Criterion], observation: VariantObservation,
           pass_threshold: int) -> GradeResult:  # fmt: skip
    results = []
    for criterion in criteria:
        outcome = EVALUATORS[criterion.check](manifest, criterion, observation)
        results.append(
            CriterionResult(
                id=criterion.id,
                check=criterion.check,
                description=criterion.description,
                required=criterion.required,
                points=criterion.points,
                awarded=criterion.points if outcome.passed else 0,
                passed=outcome.passed,
                expected=outcome.expected,
                actual=outcome.actual,
                explanation=outcome.explanation,
            )
        )
    return GradeResult(
        criteria=tuple(results),
        score=sum(result.awarded for result in results),
        max_score=sum(criterion.points for criterion in criteria),
        pass_threshold=pass_threshold,
    )


def grade(manifest: ScenarioManifest, observation: TransferObservation) -> GradeResult:
    """Apply every criterion of a version 1 scenario to its single observation, in manifest order."""
    if manifest.variants:
        raise ValueError(f"scenario {manifest.scenario.id!r} has variants; grade each one with grade_variant")
    return _grade(
        manifest, manifest.grading.criteria, VariantObservation.from_transfer(observation),
        manifest.grading.pass_threshold,
    )  # fmt: skip


def grade_variant(manifest: ScenarioManifest, observation: VariantObservation) -> GradeResult:
    """Apply the criteria for ``observation.variant``. A variant passes only when all of them pass."""
    if observation.decision not in DECISIONS:
        raise ValueError(f"decision must be one of {', '.join(DECISIONS)}, got {observation.decision!r}")
    manifest.variant(observation.variant)  # unknown variants raise KeyError
    criteria = manifest.criteria_for(observation.variant)
    return _grade(manifest, criteria, observation, sum(criterion.points for criterion in criteria))
