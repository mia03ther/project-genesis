"""Checking an untrusted payment request against what was actually authorized.

The authorization in a version 2 manifest is the source of truth: who pays,
who is paid, how much, and on which chain. A payment request arriving from a
Web2 API is untrusted input. :func:`compare_request` compares the two field by
field, exactly, and explains every mismatch so a learner can see *why* a
request must be refused.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from genesis.harness.manifest import PaymentRequest, ScenarioManifest
from genesis.harness.units import format_wei


def shorten(address: str) -> str:
    """The abbreviated form wallets often display, e.g. ``0x0000...0b0b``.

    Shown here only to teach why it is not enough: very different addresses
    can share a prefix and suffix.
    """
    return f"{address[:6]}...{address[-4:]}"


def differing_positions(first: str, second: str) -> list[int]:
    """1-based positions of the hex digits (after ``0x``) where two addresses differ."""
    a, b = first.lower().removeprefix("0x"), second.lower().removeprefix("0x")
    return [index + 1 for index, (x, y) in enumerate(zip(a, b, strict=False)) if x != y] + list(
        range(min(len(a), len(b)) + 1, max(len(a), len(b)) + 1)
    )


def describe_difference(expected: str, actual: str) -> str:
    """A sentence saying where two addresses differ, or that they are identical."""
    positions = differing_positions(expected, actual)
    if not positions:
        return "The two addresses are identical in all 40 hex digits."
    listed = ", ".join(str(p) for p in positions[:8]) + (", ..." if len(positions) > 8 else "")
    same_preview = shorten(expected) == shorten(actual)
    note = f" Both shorten to {shorten(expected)}, so a shortened preview hides the difference." if same_preview else ""
    return f"The addresses differ at hex digit(s) {listed} of 40.{note}"


@dataclass(frozen=True, slots=True)
class ConstraintCheck:
    """One field of a payment request compared with the authorization."""

    field: str
    passed: bool
    authorized: str
    requested: str
    explanation: str
    #: For the recipient field: 1-based hex digit positions that differ.
    differing_positions: tuple[int, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["differing_positions"] = list(self.differing_positions)
        return result


def compare_request(manifest: ScenarioManifest, request: PaymentRequest) -> tuple[ConstraintCheck, ...]:
    """Compare every authorized field of ``request`` exactly. Requires a version 2 manifest."""
    authorization = manifest.authorization
    if authorization is None:
        raise ValueError(f"scenario {manifest.scenario.id!r} has no authorization (manifest version 1)")
    authorized_to = manifest.account(authorization.recipient).address
    positions = tuple(differing_positions(authorized_to, request.pay_to))
    recipient = ConstraintCheck(
        field="recipient",
        passed=not positions,
        authorized=f"{authorized_to} ({authorization.recipient})",
        requested=request.pay_to,
        explanation=(
            f"The request pays {authorization.recipient}, exactly as authorized."
            if not positions
            else f"The request pays an address that is not {authorization.recipient}. "
            + describe_difference(authorized_to, request.pay_to)
        ),
        differing_positions=positions,
    )
    value = ConstraintCheck(
        field="value",
        passed=request.value == authorization.value,
        authorized=format_wei(authorization.value),
        requested=format_wei(request.value),
        explanation=(
            "The amount matches the authorization."
            if request.value == authorization.value
            else f"The request asks for {format_wei(request.value)}, "
            f"but {format_wei(authorization.value)} was authorized."
        ),
    )
    chain = ConstraintCheck(
        field="chain_id",
        passed=request.chain_id == authorization.chain_id,
        authorized=str(authorization.chain_id),
        requested=str(request.chain_id),
        explanation=(
            "The request targets the authorized chain."
            if request.chain_id == authorization.chain_id
            else f"The request targets chain {request.chain_id}, "
            f"but the payment was authorized on chain {authorization.chain_id}."
        ),
    )
    return (recipient, value, chain)
