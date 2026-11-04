"""The mission state machine: investigate, choose a strategy, replay, reset.

One :class:`MissionSession` is one player's attempt at a mission. It owns no
chain logic of its own: evidence is read through the harness's chain adapter,
every replay is executed and graded by the harness's runner and judge, and
every reset is the harness environment's verified snapshot revert. The
session only decides *which* predefined action may happen *when*.
"""

from __future__ import annotations

import enum
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from genesis import __version__
from genesis.harness.authorization import compare_request, shorten
from genesis.harness.manifest import ScenarioManifest, VariantSpec
from genesis.harness.runner import ScenarioRunner, VariantResult, build_variants_report
from genesis.harness.units import format_wei
from genesis.lab.content import ChoiceSpec, EvidenceSpec, MissionContent
from genesis.lab.policies import POLICIES, PolicyVerdict
from genesis.models import GenesisError

MISSION_REPORT_FORMAT = "genesis.mission-report"
MISSION_REPORT_VERSION = 1


class Stage(enum.StrEnum):
    INVESTIGATING = "investigating"
    DIAGNOSED = "diagnosed"
    REPLAYED = "replayed"


class MissionError(GenesisError):
    """A mission action that is not allowed right now, or refers to something unknown."""

    def __init__(self, code: str, message: str, status: int = 409) -> None:
        self.code = code
        self.status = status
        super().__init__(message)


@dataclass(frozen=True, slots=True)
class TimelineEvent:
    seq: int
    attempt: int
    kind: str
    title: str
    detail: str

    def to_dict(self) -> dict[str, Any]:
        return {"seq": self.seq, "attempt": self.attempt, "kind": self.kind, "title": self.title, "detail": self.detail}


def _amount(wei: int) -> dict[str, str]:
    return {"wei": str(wei), "ether": format_wei(wei)}


class MissionSession:
    """One attempt at a mission. Not thread-safe: callers serialize access."""

    def __init__(self, manifest: ScenarioManifest, content: MissionContent, runner: ScenarioRunner,
                 node: dict[str, Any] | None = None) -> None:  # fmt: skip
        if manifest.authorization is None or not manifest.variants:
            raise ValueError("missions need a scenario with an authorization and variants")
        self.manifest = manifest
        self.content = content
        self.runner = runner
        self.node = dict(node or {})
        self.stage = Stage.INVESTIGATING
        self.attempt = 1
        self.inspected: list[str] = []
        self.hints_revealed = 0
        self.choice: ChoiceSpec | None = None
        self.results: list[tuple[PolicyVerdict, VariantResult]] = []
        self.history: list[dict[str, Any]] = []
        self.timeline: list[TimelineEvent] = []
        self.last_report: dict[str, Any] | None = None

    # --- lifecycle -------------------------------------------------------------------

    def start(self) -> dict[str, Any]:
        """Put the chain into the scenario's starting state (verified) and open the case."""
        environment = self.runner.environment
        if environment.initialized:
            environment.reset()
        else:
            self.runner.prepare()
        self.node.setdefault("client_version", environment.client_version)
        self._event("session-started", "Case opened", self._starting_state_text())
        return self.state()

    def reset(self) -> dict[str, Any]:
        """Restore the chain snapshot (verified) and start a new attempt; investigation is kept."""
        self.runner.environment.reset()
        if self.stage is Stage.REPLAYED:
            self.attempt += 1
        self.stage = Stage.INVESTIGATING
        self.choice = None
        self.results = []
        self._event("experiment-reset", "Experiment reset", "Chain restored and verified. " + self._starting_state_text())
        return self.state()

    # --- investigation ---------------------------------------------------------------

    def inspect(self, evidence_id: str) -> dict[str, Any]:
        try:
            spec = self.content.evidence_spec(evidence_id)
        except KeyError:
            raise MissionError("unknown-evidence", f"there is no evidence called {evidence_id!r}", 404) from None
        missing = [required for required in spec.requires if required not in self.inspected]
        if missing:
            titles = ", ".join(self.content.evidence_spec(m).title for m in missing)
            raise MissionError("evidence-locked", f"inspect {titles} first")
        content = self._evidence_content(spec)
        if evidence_id not in self.inspected:
            self.inspected.append(evidence_id)
            self._event("evidence-inspected", f"Inspected: {spec.title}", spec.summary)
        return {"id": spec.id, "title": spec.title, "kind": spec.kind, "summary": spec.summary, "content": content}

    def hint(self) -> dict[str, Any]:
        hints = self.content.hints
        if self.hints_revealed >= len(hints):
            raise MissionError("no-more-hints", "every hint has already been shown")
        self.hints_revealed += 1
        text = hints[self.hints_revealed - 1]
        self._event("hint-revealed", f"Hint {self.hints_revealed} of {len(hints)}", text)
        return {"index": self.hints_revealed, "total": len(hints), "text": text}

    # --- diagnosis and replay -------------------------------------------------------------

    def choose(self, choice_id: str) -> dict[str, Any]:
        if self.stage is Stage.REPLAYED:
            raise MissionError("reset-required", "reset the experiment before choosing another strategy")
        missing = [s.title for s in self.content.evidence if s.kind in ("authorization", "request")
                   and s.id not in self.inspected]  # fmt: skip
        if missing:
            raise MissionError("investigate-first", f"inspect {', '.join(missing)} before choosing a strategy")
        try:
            choice = self.content.choice(choice_id)
        except KeyError:
            raise MissionError("unknown-choice", f"there is no strategy called {choice_id!r}", 422) from None
        self.choice = choice
        self.stage = Stage.DIAGNOSED
        self._event("strategy-chosen", f"Strategy chosen: {choice.label}", choice.detail)
        return self.state()

    def replay(self) -> dict[str, Any]:
        """Apply the chosen strategy to every variant's request on the chain, and grade it."""
        if self.stage is Stage.REPLAYED:
            raise MissionError("reset-required", "this attempt has been replayed; reset to try again")
        if self.choice is None:
            raise MissionError("choose-first", "choose a validation strategy before replaying")
        policy = POLICIES[self.choice.policy]
        results: list[tuple[PolicyVerdict, VariantResult]] = []
        for variant in self.manifest.variants:
            verdict = policy(self.manifest, variant.request)
            result = self.runner.run_variant(variant.id, verdict.as_decision(self.choice.policy))
            results.append((verdict, result))
            self._event("variant-replayed", self._replay_title(variant, result), self._replay_detail(result))
        self.results = results
        self.stage = Stage.REPLAYED
        passed = all(result.status == "passed" for _, result in results)
        self.history.append({"attempt": self.attempt, "choice": self.choice.id, "label": self.choice.label,
                             "passed": passed})  # fmt: skip
        self._event(
            "mission-passed" if passed else "mission-failed",
            "Mission complete" if passed else "Validation failed",
            self._verdict_text(passed),
        )
        self.last_report = self._build_report()
        return self.result()

    # --- views ---------------------------------------------------------------------------

    def state(self) -> dict[str, Any]:
        chain = self.runner.chain
        authorization = self.manifest.authorization
        assert authorization is not None
        can_choose = self.stage is not Stage.REPLAYED
        return {
            "stage": str(self.stage),
            "attempt": self.attempt,
            "evidence": [
                {
                    "id": spec.id,
                    "title": spec.title,
                    "kind": spec.kind,
                    "summary": spec.summary,
                    "requires": list(spec.requires),
                    "inspected": spec.id in self.inspected,
                    "locked": any(required not in self.inspected for required in spec.requires),
                }
                for spec in self.content.evidence
            ],
            "hints": {"revealed": list(self.content.hints[: self.hints_revealed]), "total": len(self.content.hints)},
            "choice": None if self.choice is None else {"id": self.choice.id, "label": self.choice.label},
            "accounts": self._accounts(),
            "chain": {"chain_id": chain.chain_id(), "block_number": chain.block_number(), **self.node},
            "timeline": [event.to_dict() for event in self.timeline],
            "result": self.result() if self.results else None,
            "history": list(self.history),
            "allowed": {
                "inspect": True,
                "hint": self.hints_revealed < len(self.content.hints),
                "choose": can_choose,
                "replay": self.stage is Stage.DIAGNOSED,
                "reset": True,
            },
        }

    def result(self) -> dict[str, Any]:
        if not self.results or self.choice is None:
            raise MissionError("not-replayed", "nothing has been replayed in this attempt", 404)
        passed = all(result.status == "passed" for _, result in self.results)
        return {
            "passed": passed,
            "attempt": self.attempt,
            "summary": self._verdict_text(passed),
            "choice": {
                "id": self.choice.id,
                "label": self.choice.label,
                "detail": self.choice.detail,
                "feedback": self.choice.feedback,
            },
            "variants": [self._variant_view(verdict, result) for verdict, result in self.results],
        }

    def report(self) -> dict[str, Any]:
        if self.last_report is None:
            raise MissionError("no-report", "replay the mission to produce a report", 404)
        return self.last_report

    # --- internals ---------------------------------------------------------------------

    def _event(self, kind: str, title: str, detail: str) -> None:
        self.timeline.append(TimelineEvent(len(self.timeline) + 1, self.attempt, kind, title, detail))

    def _role(self, label: str) -> str:
        authorization = self.manifest.authorization
        assert authorization is not None
        if label == authorization.payer:
            return "payer"
        if label == authorization.recipient:
            return "authorized recipient"
        return "not in the authorization"

    def _account(self, label: str) -> dict[str, str]:
        address = self.manifest.account(label).address
        return {"label": label, "address": address, "preview": shorten(address), "role": self._role(label)}

    def _accounts(self) -> list[dict[str, Any]]:
        chain = self.runner.chain
        rows = []
        for account in self.manifest.accounts:
            rows.append(
                {
                    **self._account(account.label),
                    "balance": _amount(chain.balance(account.address)),
                    "nonce": chain.nonce(account.address),
                }
            )
        return rows

    def _starting_state_text(self) -> str:
        parts = [f"{a.label} {format_wei(a.balance)}" for a in self.manifest.accounts]
        return "Starting balances: " + ", ".join(parts) + "."

    def _featured(self, spec: EvidenceSpec) -> VariantSpec:
        return self.manifest.variant(spec.variant or self.content.featured_variant)

    def _evidence_content(self, spec: EvidenceSpec) -> dict[str, Any]:
        authorization = self.manifest.authorization
        assert authorization is not None
        if spec.kind == "authorization":
            return {
                "reference": authorization.reference,
                "description": authorization.description,
                "payer": self._account(authorization.payer),
                "recipient": self._account(authorization.recipient),
                "value": _amount(authorization.value),
                "chain_id": authorization.chain_id,
            }
        if spec.kind == "request":
            request = self._featured(spec).request
            return {
                "source": "mock payments API (simulated, local)",
                "request_id": request.request_id,
                "pay_to": {"address": request.pay_to, "preview": shorten(request.pay_to)},
                "value": _amount(request.value),
                "chain_id": request.chain_id,
                "memo": request.memo,
                "raw": {
                    "request_id": request.request_id,
                    "pay_to": request.pay_to,
                    "amount": format_wei(request.value),
                    "chain_id": request.chain_id,
                    "memo": request.memo,
                },
            }
        if spec.kind == "transaction":
            request = self._featured(spec).request
            return {
                "from": self._account(authorization.payer),
                "to": {"address": request.pay_to, "preview": shorten(request.pay_to)},
                "value": _amount(request.value),
                "chain_id": request.chain_id,
                "gas_limit": self.manifest.transaction.gas_limit,
                "wallet_preview": f"Send {format_wei(request.value)} to {shorten(request.pay_to)}",
                "note": "A draft built from the request. Nothing has been signed or sent.",
            }
        if spec.kind == "chain":
            chain = self.runner.chain
            featured = self.manifest.variant(self.content.featured_variant).request.pay_to
            accounts = []
            for row in self._accounts():
                code = chain.code(row["address"])
                accounts.append({**row, "has_code": code not in ("0x", "0x0", ""), "paid_by_request": row["address"] == featured})
            return {"chain_id": chain.chain_id(), "block_number": chain.block_number(), "accounts": accounts, **self.node}
        checks = compare_request(self.manifest, self._featured(spec).request)
        return {
            "fields": [check.to_dict() for check in checks],
            "all_match": all(check.passed for check in checks),
        }

    def _replay_title(self, variant: VariantSpec, result: VariantResult) -> str:
        decided = "paid" if result.decision.accepted else "refused"
        return f"{variant.request.request_id}: {decided} -> {result.status}"

    def _replay_detail(self, result: VariantResult) -> str:
        transfer = result.observation.transfer
        if transfer is None:
            return "Nothing was sent; balances unchanged. Chain reset to the snapshot afterwards."
        label = self.manifest.label_of(transfer.tx_to) or transfer.tx_to
        return (
            f"Mined in block {transfer.block_number}: {format_wei(transfer.tx_value)} to {label}, "
            f"tx {transfer.tx_hash[:12]}... Chain reset to the snapshot afterwards."
        )

    def _verdict_text(self, passed: bool) -> str:
        if passed:
            return "The correct request was paid and the mismatched request was refused before signing."
        failed = [result.variant for _, result in self.results if result.status != "passed"]
        return "The strategy failed on: " + ", ".join(failed) + ". Read the failed checks, reset, and try again."

    def _variant_view(self, verdict: PolicyVerdict, result: VariantResult) -> dict[str, Any]:
        variant = self.manifest.variant(result.variant)
        observation = result.observation
        transfer = observation.transfer
        transaction = None
        if transfer is not None:
            transaction = {
                "hash": transfer.tx_hash,
                "block_number": transfer.block_number,
                "from": self._account(self.manifest.label_of(transfer.tx_from) or ""),
                "to": {
                    "address": transfer.tx_to,
                    "preview": shorten(transfer.tx_to or ""),
                    "label": self.manifest.label_of(transfer.tx_to),
                },
                "value": _amount(transfer.tx_value),
                "gas_used": transfer.gas_used,
                "effective_gas_price_wei": str(transfer.effective_gas_price),
                "fee": _amount(transfer.fee),
                "status": transfer.status,
            }
        return {
            "id": variant.id,
            "title": variant.title,
            "description": variant.description,
            "expect": variant.expect,
            "request": {
                "request_id": variant.request.request_id,
                "pay_to": {"address": variant.request.pay_to, "preview": shorten(variant.request.pay_to)},
                "value": _amount(variant.request.value),
                "chain_id": variant.request.chain_id,
            },
            "decision": {
                "accepted": verdict.accepted,
                "summary": verdict.summary,
                "checks": [{"field": c.field, "passed": c.passed, "detail": c.detail} for c in verdict.checks],
            },
            "status": result.status,
            "score": result.grade.score,
            "max_score": result.grade.max_score,
            "transaction": transaction,
            "balances": [
                {
                    "label": account.label,
                    "address": account.address,
                    "before": _amount(observation.balances_before[account.label]),
                    "after": _amount(observation.balances_after[account.label]),
                    "change": _amount(observation.balances_after[account.label]
                                      - observation.balances_before[account.label]),
                }
                for account in self.manifest.accounts
            ],
            "criteria": [criterion.to_dict() for criterion in result.grade.criteria],
            "normalized_digest": result.normalized_digest(self.manifest),
            "reset_verified": result.reset_verified,
        }

    def _build_report(self) -> dict[str, Any]:
        assert self.choice is not None
        harness = build_variants_report(
            self.manifest, f"policy:{self.choice.policy}", self.node,
            [(1, result) for _, result in self.results], None,
        )  # fmt: skip
        passed = harness["status"] == "passed"
        return {
            "report_format": MISSION_REPORT_FORMAT,
            "report_version": MISSION_REPORT_VERSION,
            "genesis_version": __version__,
            "mission": {
                "id": self.content.id,
                "title": self.content.title,
                "attempt": self.attempt,
                "choice": {"id": self.choice.id, "label": self.choice.label, "policy": self.choice.policy},
                "evidence_inspected": list(self.inspected),
                "hints_used": self.hints_revealed,
            },
            "verdict": "passed" if passed else "failed",
            "harness_report": harness,
        }


SessionFactory = Callable[[], MissionSession]

