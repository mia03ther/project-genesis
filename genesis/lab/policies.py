"""Validation strategies a player can choose for a payment request.

Each strategy is a fixed, side-effect-free function that the server runs; the
browser can only pick one by id. Strategies model common real-world habits, of
which only one is safe. They decide; they do not grade. Whether a decision was
right is established afterwards by the harness's judge from chain evidence.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from types import MappingProxyType

from genesis.harness.authorization import compare_request, shorten
from genesis.harness.manifest import PaymentRequest, ScenarioManifest
from genesis.harness.runner import VariantDecision
from genesis.harness.units import format_wei


@dataclass(frozen=True, slots=True)
class PolicyCheck:
    """One thing a strategy looked at, and what it concluded."""

    field: str
    passed: bool
    detail: str


@dataclass(frozen=True, slots=True)
class PolicyVerdict:
    accepted: bool
    checks: tuple[PolicyCheck, ...]
    summary: str

    def as_decision(self, policy_id: str) -> VariantDecision:
        reasons = (self.summary, *(f"{c.field}: {c.detail}" for c in self.checks))
        return VariantDecision(accepted=self.accepted, reasons=reasons, decided_by=f"policy:{policy_id}")


Policy = Callable[[ScenarioManifest, PaymentRequest], PolicyVerdict]


def _authorized_recipient(manifest: ScenarioManifest) -> str:
    if manifest.authorization is None:
        raise ValueError("strategies need a scenario with an authorization (manifest version 2)")
    return manifest.account(manifest.authorization.recipient).address


def trust_api(manifest: ScenarioManifest, request: PaymentRequest) -> PolicyVerdict:
    """Pay whatever the API asks: nothing is compared with the authorization."""
    _authorized_recipient(manifest)
    return PolicyVerdict(True, (), "Paid as received: the request was trusted without comparing it to anything.")


def preview_match(manifest: ScenarioManifest, request: PaymentRequest) -> PolicyVerdict:
    """Compare only the shortened address a wallet preview shows, plus the amount."""
    authorized = _authorized_recipient(manifest)
    assert manifest.authorization is not None
    preview_ok = shorten(request.pay_to) == shorten(authorized)
    value_ok = request.value == manifest.authorization.value
    checks = (
        PolicyCheck(
            "recipient preview",
            preview_ok,
            f"{shorten(request.pay_to)} {'matches' if preview_ok else 'differs from'} {shorten(authorized)}",
        ),
        PolicyCheck("value", value_ok, f"{format_wei(request.value)} requested"),
    )
    accepted = preview_ok and value_ok
    summary = (
        "Paid: the shortened preview and the amount matched."
        if accepted
        else "Refused: the shortened preview or the amount did not match."
    )
    return PolicyVerdict(accepted, checks, summary)


def amount_and_network(manifest: ScenarioManifest, request: PaymentRequest) -> PolicyVerdict:
    """Check the amount and the chain exactly, but never the recipient."""
    checks = tuple(
        PolicyCheck(check.field, check.passed, check.explanation)
        for check in compare_request(manifest, request)
        if check.field in ("value", "chain_id")
    )
    accepted = all(check.passed for check in checks)
    summary = (
        "Paid: the amount and the chain matched (the recipient was not checked)."
        if accepted
        else "Refused: the amount or the chain did not match."
    )
    return PolicyVerdict(accepted, checks, summary)


def exact_intent_match(manifest: ScenarioManifest, request: PaymentRequest) -> PolicyVerdict:
    """Compare every authorized field exactly; refuse on any mismatch."""
    checks = tuple(
        PolicyCheck(check.field, check.passed, check.explanation) for check in compare_request(manifest, request)
    )
    accepted = all(check.passed for check in checks)
    mismatched = [check.field for check in checks if not check.passed]
    summary = (
        "Paid: recipient, amount and chain all exactly match the authorization."
        if accepted
        else f"Refused before signing: {', '.join(mismatched)} does not match the authorization."
    )
    return PolicyVerdict(accepted, checks, summary)


def refuse_all(manifest: ScenarioManifest, request: PaymentRequest) -> PolicyVerdict:
    """Refuse every request without looking at it."""
    _authorized_recipient(manifest)
    return PolicyVerdict(False, (), "Refused: every API payment request is refused, whatever it says.")


POLICIES: Mapping[str, Policy] = MappingProxyType(
    {
        "trust-api": trust_api,
        "preview-match": preview_match,
        "amount-and-network": amount_and_network,
        "exact-intent-match": exact_intent_match,
        "refuse-all": refuse_all,
    }
)
