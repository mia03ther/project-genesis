"""Actors, the run loop and the JSON report.

An *actor* is whoever performs the scenario's action. Phase 1 ships the
:class:`ReferenceActor`, which submits exactly what the task asks for, and the
:class:`ScriptedActor`, which submits a fixed transfer (useful for seeing how
the judge treats a mistake). A future learner interface or language-model
adapter is just another :class:`Actor`. Whatever an actor returns is validated
by the runner before anything is sent to the chain.
"""

from __future__ import annotations

import json
import os
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol

from genesis import __version__
from genesis.harness.chain import (
    AnvilChain,
    AnvilProcess,
    ChainError,
    JsonRpcClient,
    RpcError,
    from_hex,
    to_hex,
)
from genesis.harness.environment import AccountState, ScenarioEnvironment
from genesis.harness.grading import (
    ENVIRONMENT_SPECIFIC_FIELDS,
    GradeResult,
    TransferObservation,
    VariantObservation,
    digest,
    grade,
    grade_variant,
)
from genesis.harness.manifest import MAX_GAS_LIMIT, SIMPLE_TRANSFER_GAS, ScenarioManifest, VariantSpec
from genesis.harness.units import MAX_UINT256, format_wei
from genesis.models import GenesisError, is_int

REPORT_FORMAT = "genesis.scenario-report"
REPORT_VERSION = 1
#: Reports of version 2 scenarios list one result per variant (and repeat) instead of runs.
VARIANTS_REPORT_VERSION = 2

NORMALIZATION_NOTE = (
    "Transaction and block hashes, block numbers, gas prices and fees depend on the node and its "
    "configuration, so they are recorded under environment_specific and never compared. The "
    "normalized observation holds only values fixed by the scenario; repeated runs must produce the "
    "same normalized digest."
)


@dataclass(frozen=True, slots=True)
class Submission:
    """A proposed transfer in scenario terms: account labels and an amount in wei."""

    sender: str
    recipient: str
    value: int
    gas_limit: int = SIMPLE_TRANSFER_GAS

    def to_dict(self) -> dict[str, Any]:
        return {
            "from": self.sender,
            "to": self.recipient,
            "value_wei": str(self.value),
            "gas_limit": self.gas_limit,
        }


@dataclass(frozen=True, slots=True)
class TaskAccount:
    label: str
    address: str
    balance: int


@dataclass(frozen=True, slots=True)
class TransferTask:
    """What an actor is told: the goal and the accounts, never the grading rules."""

    scenario_id: str
    title: str
    instructions: str
    accounts: tuple[TaskAccount, ...]
    requested: Submission

    @classmethod
    def from_manifest(cls, manifest: ScenarioManifest) -> TransferTask:
        transfer = manifest.transaction
        return cls(
            scenario_id=manifest.scenario.id,
            title=manifest.scenario.title,
            instructions=f"Send {format_wei(transfer.value)} from {transfer.sender} to {transfer.recipient}.",
            accounts=tuple(TaskAccount(a.label, a.address, a.balance) for a in manifest.accounts),
            requested=Submission(transfer.sender, transfer.recipient, transfer.value, transfer.gas_limit),
        )


class Actor(Protocol):
    @property
    def name(self) -> str: ...

    def submit(self, task: TransferTask) -> Submission: ...


@dataclass(frozen=True, slots=True)
class ReferenceActor:
    """Submits exactly the transfer the task requests: the scenario's reference solution."""

    name: str = "reference"

    def submit(self, task: TransferTask) -> Submission:
        return task.requested


@dataclass(frozen=True, slots=True)
class ScriptedActor:
    """Submits a fixed transfer, whatever the task says."""

    submission: Submission
    name: str = "scripted"

    def submit(self, task: TransferTask) -> Submission:
        return self.submission


def validate_submission(manifest: ScenarioManifest, submission: object) -> list[str]:
    """Reasons the runner refuses to send a submission (empty when it may be sent)."""
    if not isinstance(submission, Submission):
        return [f"the actor returned {type(submission).__name__}, expected a Submission"]
    problems = []
    labels = {account.label for account in manifest.accounts}
    for role, label in (("sender", submission.sender), ("recipient", submission.recipient)):
        if label not in labels:
            problems.append(f"{role} {label!r} is not one of the scenario's accounts")
    if not is_int(submission.value) or not 0 <= submission.value <= MAX_UINT256:
        problems.append(f"value {submission.value!r} must be a whole number of wei between 0 and 2**256 - 1")
    if not is_int(submission.gas_limit) or not SIMPLE_TRANSFER_GAS <= submission.gas_limit <= MAX_GAS_LIMIT:
        problems.append(
            f"gas limit {submission.gas_limit!r} must be between {SIMPLE_TRANSFER_GAS} and {MAX_GAS_LIMIT}"
        )
    return problems


@dataclass(frozen=True, slots=True)
class RunResult:
    index: int
    #: ``passed`` or ``failed`` once graded; ``rejected`` if nothing could be executed.
    status: str
    actor: str
    submission: Mapping[str, Any] | None
    problems: tuple[str, ...] = ()
    observation: TransferObservation | None = None
    grade: GradeResult | None = None
    reset_verified: bool = False

    def normalized_digest(self, manifest: ScenarioManifest) -> str | None:
        """Digest of everything about the run that must not vary between environments."""
        if self.observation is None or self.grade is None:
            return None
        outcome = {
            "observation": self.observation.normalized(manifest),
            "criteria": {result.id: result.passed for result in self.grade.criteria},
            "score": self.grade.score,
        }
        return digest(outcome)

    def to_dict(self, manifest: ScenarioManifest) -> dict[str, Any]:
        observation = None
        if self.observation is not None:
            observation = {
                "normalized": self.observation.normalized(manifest),
                "environment_specific": self.observation.environment_specific(),
            }
        return {
            "run": self.index,
            "status": self.status,
            "actor": self.actor,
            "submission": dict(self.submission) if self.submission is not None else None,
            "rejection_reasons": list(self.problems),
            "grading": self.grade.to_dict() if self.grade is not None else None,
            "observation": observation,
            "normalized_digest": self.normalized_digest(manifest),
            "reset_verified": self.reset_verified,
        }


@dataclass(frozen=True, slots=True)
class VariantDecision:
    """What a validator decided about one variant's payment request, and why."""

    accepted: bool
    reasons: tuple[str, ...] = ()
    #: Who decided, e.g. ``reference`` or ``policy:exact-intent-match``.
    decided_by: str = "reference"


def reference_decision(variant: VariantSpec) -> VariantDecision:
    """The dataset's own answer: accept exactly the variants it expects to be accepted."""
    return VariantDecision(
        accepted=variant.expect == "accept",
        reasons=(f"the scenario expects this request to be {variant.expect}ed",),
        decided_by="reference",
    )


@dataclass(frozen=True, slots=True)
class VariantResult:
    variant: str
    #: ``passed`` or ``failed``: whether every criterion for the variant passed.
    status: str
    decision: VariantDecision
    submission: Submission | None
    observation: VariantObservation
    grade: GradeResult
    reset_verified: bool = False

    def normalized_digest(self, manifest: ScenarioManifest) -> str:
        """Digest of everything about the run that must not vary between environments."""
        outcome = {
            "observation": self.observation.normalized(manifest),
            "criteria": {result.id: result.passed for result in self.grade.criteria},
            "score": self.grade.score,
        }
        return digest(outcome)

    def to_dict(self, manifest: ScenarioManifest) -> dict[str, Any]:
        variant = manifest.variant(self.variant)
        observation = self.observation
        request = variant.request
        return {
            "variant": self.variant,
            "title": variant.title,
            "expect": variant.expect,
            "status": self.status,
            "decision": {
                "accepted": self.decision.accepted,
                "decided_by": self.decision.decided_by,
                "reasons": list(observation.reasons),
            },
            "request": {
                "request_id": request.request_id,
                "pay_to": request.pay_to,
                "value_wei": str(request.value),
                "chain_id": request.chain_id,
                "memo": request.memo,
            },
            "submission": self.submission.to_dict() if self.submission is not None else None,
            "grading": self.grade.to_dict(),
            "observation": {
                "normalized": observation.normalized(manifest),
                "environment_specific": observation.environment_specific(),
            },
            "balances": [
                {
                    "label": account.label,
                    "address": account.address,
                    "before_wei": str(observation.balances_before[account.label]),
                    "after_wei": str(observation.balances_after[account.label]),
                    "change_wei": str(
                        observation.balances_after[account.label] - observation.balances_before[account.label]
                    ),
                }
                for account in manifest.accounts
            ],
            "normalized_digest": self.normalized_digest(manifest),
            "reset_verified": self.reset_verified,
        }


class ScenarioRunner:
    """Runs a scenario's action on an initialized environment and restores it afterwards."""

    def __init__(self, manifest: ScenarioManifest, chain: AnvilChain) -> None:
        self.manifest = manifest
        self.chain = chain
        self.environment = ScenarioEnvironment(chain, manifest)

    def prepare(self) -> None:
        self.environment.initialize()

    def run_once(self, actor: Actor, *, index: int = 1) -> RunResult:
        """Ask the actor, validate, execute, observe, grade, and reset the chain."""
        if not self.environment.initialized:
            self.prepare()
        submission = actor.submit(TransferTask.from_manifest(self.manifest))
        described = submission.to_dict() if isinstance(submission, Submission) else None
        problems = validate_submission(self.manifest, submission)
        if problems:
            self.environment.reset()  # nothing was sent; reset proves it
            return RunResult(index, "rejected", actor.name, described, tuple(problems), reset_verified=True)
        assert isinstance(submission, Submission)  # established by validate_submission

        executed = self._execute(submission, self.environment.state())
        if isinstance(executed, str):
            self.environment.reset()
            return RunResult(index, "rejected", actor.name, described, (executed,), reset_verified=True)
        result = grade(self.manifest, executed)
        self.environment.reset()
        status = "passed" if result.passed else "failed"
        return RunResult(index, status, actor.name, described, (), executed, result, reset_verified=True)

    def run_variant(self, variant_id: str, decision: VariantDecision) -> VariantResult:
        """Apply a decision to one variant's request, observe, grade, and reset the chain.

        If the request is accepted, the authorized payer pays exactly what the
        *request* says, whatever the authorization says: that is how an
        unsafe validator's mistake reaches the chain, where the judge sees it.
        If it is refused, nothing is sent and the unchanged state is recorded.
        """
        if not self.environment.initialized:
            self.prepare()
        variant = self.manifest.variant(variant_id)
        authorization = self.manifest.authorization
        if authorization is None:
            raise ValueError(f"scenario {self.manifest.scenario.id!r} has no variants (manifest version 1)")
        before = self.environment.state()
        reasons = list(decision.reasons)
        submission: Submission | None = None
        transfer: TransferObservation | None = None
        if decision.accepted:
            recipient = self.manifest.label_of(variant.request.pay_to)
            if recipient is None:  # excluded by manifest validation
                raise ValueError(f"variant {variant_id!r} pays an address outside the scenario")
            submission = Submission(
                authorization.payer, recipient, variant.request.value, self.manifest.transaction.gas_limit
            )
            executed = self._execute(submission, before)
            if isinstance(executed, str):
                reasons.append(executed)
            else:
                transfer = executed
        after = self.environment.state()
        observation = VariantObservation(
            variant=variant.id,
            decision="accepted" if decision.accepted else "rejected",
            reasons=tuple(reasons),
            chain_id=self.chain.chain_id(),
            transfer=transfer,
            balances_before={label: state.balance for label, state in before.items()},
            balances_after={label: state.balance for label, state in after.items()},
            nonces_before={label: state.nonce for label, state in before.items()},
            nonces_after={label: state.nonce for label, state in after.items()},
        )
        result = grade_variant(self.manifest, observation)
        self.environment.reset()
        status = "passed" if result.passed else "failed"
        return VariantResult(variant.id, status, decision, submission, observation, result, reset_verified=True)

    def _execute(self, submission: Submission, before: Mapping[str, AccountState]) -> TransferObservation | str:
        """Send a validated submission and observe it; a refusal by the chain is returned as text."""
        sender = self.manifest.account(submission.sender)
        recipient = self.manifest.account(submission.recipient)
        request = {
            "from": sender.address,
            "to": recipient.address,
            "value": to_hex(submission.value),
            "gas": to_hex(submission.gas_limit),
        }
        try:
            tx_hash = self.chain.send_transaction(request)
        except RpcError as error:
            return f"the chain refused it: {error}"
        receipt = self.chain.receipt(tx_hash)
        transaction = self.chain.transaction(tx_hash)
        after = self.environment.state()
        return _observe(self.manifest, self.environment.client_version or "", tx_hash, transaction, receipt,
                        before, after, self.chain.chain_id())  # fmt: skip


def _observe(manifest: ScenarioManifest, client_version: str, tx_hash: str, transaction: Mapping[str, Any],
             receipt: Mapping[str, Any], before: Mapping[str, AccountState], after: Mapping[str, AccountState],
             chain_id: int) -> TransferObservation:  # fmt: skip
    try:
        tx_type = transaction.get("type")
        return TransferObservation(
            chain_id=chain_id,
            client_version=client_version,
            tx_hash=str(receipt["transactionHash"]),
            tx_from=str(transaction["from"]).lower(),
            tx_to=str(transaction["to"]).lower() if transaction.get("to") else None,
            tx_value=from_hex(transaction["value"]),
            tx_nonce=from_hex(transaction["nonce"]),
            tx_gas_limit=from_hex(transaction["gas"]),
            tx_type=from_hex(tx_type) if tx_type is not None else None,
            status=from_hex(receipt["status"]),
            gas_used=from_hex(receipt["gasUsed"]),
            effective_gas_price=from_hex(receipt["effectiveGasPrice"]),
            block_number=from_hex(receipt["blockNumber"]),
            block_hash=str(receipt["blockHash"]),
            balances_before={label: state.balance for label, state in before.items()},
            balances_after={label: state.balance for label, state in after.items()},
            nonces_before={label: state.nonce for label, state in before.items()},
            nonces_after={label: state.nonce for label, state in after.items()},
        )
    except KeyError as missing:
        raise ChainError(f"transaction {tx_hash}: the node omitted field {missing}") from None


@dataclass(slots=True)
class _Session:
    environment: dict[str, Any] = field(default_factory=dict)
    runs: list[RunResult] = field(default_factory=list)
    error: str | None = None


def run_scenario(manifest: ScenarioManifest, *, actor: Actor | None = None, repeat: int = 1,
                 rpc_url: str | None = None, anvil_executable: str = "anvil") -> dict[str, Any]:  # fmt: skip
    """Run a scenario ``repeat`` times from the same initial state and return the JSON report.

    Without ``rpc_url`` a private ``anvil`` process is started for the session
    and stopped afterwards; with it, an existing local Anvil node is used. Any
    failure of the environment is reported with status ``error`` rather than raised.
    """
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    actor = actor if actor is not None else ReferenceActor()
    session = _Session(environment={"kind": manifest.environment.kind, "managed_node": rpc_url is None})
    process: AnvilProcess | None = None
    try:
        if rpc_url is None:
            process = AnvilProcess(anvil_executable, chain_id=manifest.environment.chain_id)
            rpc_url = process.start()
        chain = AnvilChain(JsonRpcClient(rpc_url))
        runner = ScenarioRunner(manifest, chain)
        runner.prepare()
        session.environment |= {
            "client_version": runner.environment.client_version,
            "chain_id": chain.chain_id(),
            "rpc_url": rpc_url,
        }
        for index in range(1, repeat + 1):
            session.runs.append(runner.run_once(actor, index=index))
    except GenesisError as error:
        session.error = str(error)
    finally:
        if process is not None:
            process.stop()
    return build_report(manifest, actor.name, session.environment, session.runs, session.error)


def run_variants(manifest: ScenarioManifest, *, decide: Callable[[VariantSpec], VariantDecision] | None = None,
                 decided_by: str = "reference", repeat: int = 1, rpc_url: str | None = None,
                 anvil_executable: str = "anvil") -> dict[str, Any]:  # fmt: skip
    """Run every variant of a version 2 scenario, ``repeat`` times, and return the JSON report.

    ``decide`` turns each variant into a decision; by default the scenario's
    own expectation (the reference solution). The chain is reset after every
    variant, so each one starts from the same initial state.
    """
    if not manifest.variants:
        raise ValueError(f"scenario {manifest.scenario.id!r} has no variants; use run_scenario")
    if repeat < 1:
        raise ValueError("repeat must be at least 1")
    decide = decide if decide is not None else reference_decision
    environment: dict[str, Any] = {"kind": manifest.environment.kind, "managed_node": rpc_url is None}
    results: list[tuple[int, VariantResult]] = []
    error: str | None = None
    process: AnvilProcess | None = None
    try:
        if rpc_url is None:
            process = AnvilProcess(anvil_executable, chain_id=manifest.environment.chain_id)
            rpc_url = process.start()
        chain = AnvilChain(JsonRpcClient(rpc_url))
        runner = ScenarioRunner(manifest, chain)
        runner.prepare()
        environment |= {
            "client_version": runner.environment.client_version,
            "chain_id": chain.chain_id(),
            "rpc_url": rpc_url,
        }
        for index in range(1, repeat + 1):
            for variant in manifest.variants:
                results.append((index, runner.run_variant(variant.id, decide(variant))))
    except GenesisError as failure:
        error = str(failure)
    finally:
        if process is not None:
            process.stop()
    return build_variants_report(manifest, decided_by, environment, results, error)


def build_variants_report(manifest: ScenarioManifest, decided_by: str, environment: Mapping[str, Any],
                          results: list[tuple[int, VariantResult]], error: str | None) -> dict[str, Any]:  # fmt: skip
    """The report of a variant session (report version 2). Like version 1 it has no timestamps."""
    digests: dict[str, list[str]] = {variant.id: [] for variant in manifest.variants}
    for _, result in results:
        digests[result.variant].append(result.normalized_digest(manifest))
    consistent = all(len(set(values)) <= 1 for values in digests.values())
    if error is None and not results:
        error = "no variants were run"
    if error is None and not consistent:
        error = "repeated runs from the same initial state produced different outcomes"
    if error is not None:
        status = "error"
    elif any(result.status == "failed" for _, result in results):
        status = "failed"
    else:
        status = "passed"
    return {
        "report_format": REPORT_FORMAT,
        "report_version": VARIANTS_REPORT_VERSION,
        "genesis_version": __version__,
        "status": status,
        "error": error,
        "scenario": {
            "id": manifest.scenario.id,
            "version": manifest.scenario.version,
            "title": manifest.scenario.title,
            "manifest_version": manifest.manifest_version,
            "manifest_digest": manifest.digest(),
            "source": manifest.source,
        },
        "decided_by": decided_by,
        "environment": dict(environment),
        "summary": {
            "variants": len(manifest.variants),
            "runs": len(results),
            "passed_runs": sum(1 for _, result in results if result.status == "passed"),
        },
        "variants": [{**result.to_dict(manifest), "repeat": index} for index, result in results],
        "reproducibility": {
            "normalized_digests": digests,
            "consistent": consistent,
            "environment_specific_fields": list(ENVIRONMENT_SPECIFIC_FIELDS),
            "note": NORMALIZATION_NOTE,
        },
    }


def build_report(manifest: ScenarioManifest, actor: str, environment: Mapping[str, Any],
                 runs: list[RunResult], error: str | None) -> dict[str, Any]:  # fmt: skip
    """Assemble the machine-readable report. It contains no timestamps: everything
    outside the ``environment`` and ``environment_specific`` sections is reproducible."""
    digests = [d for d in (run.normalized_digest(manifest) for run in runs) if d is not None]
    consistent = len(set(digests)) <= 1
    if error is None and not runs:
        error = "no runs were executed"
    if error is None and not consistent:
        error = "repeated runs from the same initial state produced different outcomes"
    if error is not None:
        status = "error"
    elif any(run.status == "failed" for run in runs):
        status = "failed"
    elif any(run.status == "rejected" for run in runs):
        status = "rejected"
    else:
        status = "passed"
    graded = next((run.grade for run in runs if run.grade is not None), None)
    return {
        "report_format": REPORT_FORMAT,
        "report_version": REPORT_VERSION,
        "genesis_version": __version__,
        "status": status,
        "error": error,
        "scenario": {
            "id": manifest.scenario.id,
            "version": manifest.scenario.version,
            "title": manifest.scenario.title,
            "manifest_version": manifest.manifest_version,
            "manifest_digest": manifest.digest(),
            "source": manifest.source,
        },
        "actor": actor,
        "environment": dict(environment),
        "summary": {
            "runs": len(runs),
            "passed_runs": sum(1 for run in runs if run.status == "passed"),
            "score": graded.score if graded else None,
            "max_score": manifest.grading.max_score,
            "pass_threshold": manifest.grading.pass_threshold,
        },
        "runs": [run.to_dict(manifest) for run in runs],
        "reproducibility": {
            "normalized_digests": digests,
            "consistent": consistent,
            "environment_specific_fields": list(ENVIRONMENT_SPECIFIC_FIELDS),
            "note": NORMALIZATION_NOTE,
        },
    }


def write_report(report: Mapping[str, Any], path: str | os.PathLike[str]) -> Path:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
    return target
