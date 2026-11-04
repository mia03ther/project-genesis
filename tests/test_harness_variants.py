"""Manifest version 2: authorization, variants, the new checks, and variant replay."""

from __future__ import annotations

import copy
import json
import tomllib
from collections.abc import Callable
from typing import Any

import pytest

from genesis.harness.authorization import compare_request, describe_difference, differing_positions, shorten
from genesis.harness.chain import AnvilChain
from genesis.harness.grading import VariantObservation, grade, grade_variant
from genesis.harness.manifest import CHECKS, ManifestError, load_manifest, parse_manifest
from genesis.harness.runner import (
    VARIANTS_REPORT_VERSION,
    ScenarioRunner,
    VariantDecision,
    reference_decision,
    run_variants,
)
from tests.fake_anvil import FakeAnvil, FakeAnvilServer
from tests.harness_support import ETHER, FIRST_TRANSFER, SCENARIOS, first_transfer, observation

WRONG_RECIPIENT = SCENARIOS / "wrong-recipient"
BOB = "0x0000000000000000000000000000000000000b0b"
UNKNOWN = "0x00000000000000000000000000000000000f0b0b"
_RAW = tomllib.loads((WRONG_RECIPIENT / "scenario.toml").read_text(encoding="utf-8"))

#: Normalized digests of the reference decisions for each variant, observed identically on
#: Anvil 1.8.7 and on the test double. Change only with a deliberate change to the scenario.
REFERENCE_VARIANT_DIGESTS = {
    "authorized-request": "8771802e3818601b",
    "wrong-recipient": "16a3d9c2636fbed7",
}


def raw() -> dict[str, Any]:
    return copy.deepcopy(_RAW)


def mission_manifest():  # type: ignore[no-untyped-def]
    return load_manifest(WRONG_RECIPIENT)


# --- manifest -------------------------------------------------------------------------


def test_version_1_manifests_are_unchanged() -> None:
    assert first_transfer().digest() == "66d982a9cb9938722088c23cc5c23a6a833569079b6a8c072900dcb7a547b602"
    assert "authorization" not in first_transfer().to_dict()


def test_mission_manifest_loads() -> None:
    manifest = mission_manifest()
    assert manifest.manifest_version == 2
    assert manifest.authorization is not None
    assert (manifest.authorization.payer, manifest.authorization.recipient) == ("alice", "bob")
    assert manifest.authorization.value == 15 * ETHER // 10
    assert [(v.id, v.expect) for v in manifest.variants] == [("authorized-request", "accept"), ("wrong-recipient", "reject")]
    assert manifest.variant("wrong-recipient").request.pay_to == UNKNOWN
    assert {c.id for c in manifest.criteria_for("wrong-recipient")} == {
        "correct-decision", "only-authorized-transfers", "nothing-moved"}  # fmt: skip
    assert len(manifest.criteria_for("authorized-request")) == 8
    data = manifest.to_dict()
    assert data["authorization"]["value_wei"] == "1500000000000000000"
    assert all("variants" in criterion for criterion in data["grading"]["criteria"])


def test_version_2_digest_is_stable_and_content_sensitive() -> None:
    assert mission_manifest().digest() == mission_manifest().digest()
    data = raw()
    data["variants"][1]["request"]["pay_to"] = BOB
    assert parse_manifest(data).digest() != mission_manifest().digest()


Mutation = Callable[[dict[str, Any]], None]

INVALID_V2: list[tuple[str, Mutation, str]] = [
    ("missing authorization", lambda d: d.pop("authorization"), "manifest.authorization: is required"),
    ("missing variants", lambda d: d.pop("variants"), "manifest.variants: is required"),
    ("unknown payer", lambda d: d["authorization"].update(payer="carol"), "authorization.payer: 'carol'"),
    ("self payment", lambda d: d["authorization"].update(recipient="alice"), "authorization.recipient: must differ"),
    ("zero value", lambda d: d["authorization"].update(value="0 ether"), "authorization.value: must be more than zero"),
    ("other chain", lambda d: d["authorization"].update(chain_id=1), "authorization.chain_id: must equal"),
    ("bad expectation", lambda d: d["variants"][0].update(expect="maybe"), "variants[0].expect: must be one of"),
    ("duplicate variant", lambda d: d["variants"][1].update(id="authorized-request"), "duplicate variant id"),
    ("outside address", lambda d: d["variants"][1]["request"].update(pay_to="0x" + "12" * 20),
     "must be the address of one of the scenario's accounts"),
    ("bad request field", lambda d: d["variants"][1]["request"].update(signature="0x00"),
     "variants[1].request.signature: is not a known field"),
    ("reference mismatch", lambda d: d["transaction"].update(to="unknown"), "transaction: must be the authorized transfer"),
    ("unknown variant filter", lambda d: d["grading"]["criteria"][2].update(variants=["nope"]),
     "'nope' is not one of the scenario's variants"),
    ("threshold in v2", lambda d: d["grading"].update(pass_threshold=1), "grading.pass_threshold: is not a known field"),
]  # fmt: skip


@pytest.mark.parametrize(("mutate", "message"), [c[1:] for c in INVALID_V2], ids=[c[0] for c in INVALID_V2])
def test_invalid_version_2_manifests_are_rejected(mutate: Mutation, message: str) -> None:
    data = raw()
    mutate(data)
    with pytest.raises(ManifestError) as caught:
        parse_manifest(data)
    assert any(message in problem for problem in caught.value.errors), caught.value.errors


def test_version_2_checks_are_refused_in_version_1() -> None:
    data = tomllib.loads((FIRST_TRANSFER / "scenario.toml").read_text(encoding="utf-8"))
    data["grading"]["criteria"].append({"id": "x", "check": "decision", "description": "d"})
    with pytest.raises(ManifestError, match="check 'decision' needs manifest_version 2"):
        parse_manifest(data)
    data = tomllib.loads((FIRST_TRANSFER / "scenario.toml").read_text(encoding="utf-8"))
    data["grading"]["criteria"][0]["variants"] = ["a"]
    with pytest.raises(ManifestError, match="variants: is not a known field"):
        parse_manifest(data)


def test_every_version_2_check_is_declared() -> None:
    assert {name for name, spec in CHECKS.items() if spec.since == 2} == {
        "decision", "authorized_transfer", "balances_unchanged"}  # fmt: skip


# --- exact comparison -------------------------------------------------------------------


def test_shortened_previews_hide_the_difference() -> None:
    assert shorten(BOB) == shorten(UNKNOWN) == "0x0000...0b0b"
    assert differing_positions(BOB, UNKNOWN) == [36]
    assert differing_positions(BOB, BOB) == []
    assert "differ at hex digit(s) 36 of 40" in describe_difference(BOB, UNKNOWN)
    assert "Both shorten to 0x0000...0b0b" in describe_difference(BOB, UNKNOWN)


def test_compare_request_checks_every_authorized_field() -> None:
    manifest = mission_manifest()
    good = {check.field: check.passed for check in compare_request(manifest, manifest.variant("authorized-request").request)}
    bad = compare_request(manifest, manifest.variant("wrong-recipient").request)
    assert good == {"recipient": True, "value": True, "chain_id": True}
    assert [(c.field, c.passed) for c in bad] == [("recipient", False), ("value", True), ("chain_id", True)]
    assert bad[0].differing_positions == (36,)
    json.dumps([check.to_dict() for check in bad])


def test_compare_request_needs_an_authorization() -> None:
    manifest = first_transfer()
    with pytest.raises(ValueError, match="no authorization"):
        compare_request(manifest, mission_manifest().variants[0].request)


# --- the judge ------------------------------------------------------------------------------


def _refused(variant: str) -> VariantObservation:
    balances = {"alice": 10 * ETHER, "bob": 0, "unknown": 0}
    nonces = {"alice": 0, "bob": 0, "unknown": 0}
    return VariantObservation(variant, "rejected", ("refused",), 31337, None, balances, balances, nonces, nonces)


def _paid(variant: str, to: str, value: int = 15 * ETHER // 10) -> VariantObservation:
    gas_price, fee = 10**9, 21_000 * 10**9
    labels = {BOB: "bob", UNKNOWN: "unknown"}
    seen = observation(value=value, to=to, gas_price=gas_price)
    after = {"alice": 10 * ETHER - value - fee, "bob": 0, "unknown": 0}
    after[labels[to]] = value
    transfer = type(seen)(**{**{f: getattr(seen, f) for f in seen.__dataclass_fields__},
                             "balances_before": {"alice": 10 * ETHER, "bob": 0, "unknown": 0},
                             "balances_after": after,
                             "nonces_before": {"alice": 0, "bob": 0, "unknown": 0},
                             "nonces_after": {"alice": 1, "bob": 0, "unknown": 0}})  # fmt: skip
    return VariantObservation(variant, "accepted", ("paid",), 31337, transfer, transfer.balances_before,
                              transfer.balances_after, transfer.nonces_before, transfer.nonces_after)  # fmt: skip


def _failed(result: Any) -> set[str]:
    return {c.id for c in result.criteria if not c.passed}


def test_reference_outcomes_pass() -> None:
    manifest = mission_manifest()
    paid = grade_variant(manifest, _paid("authorized-request", BOB))
    refused = grade_variant(manifest, _refused("wrong-recipient"))
    assert paid.passed and paid.score == paid.max_score == 15
    assert refused.passed and refused.score == refused.max_score == 9
    assert all(criterion.explanation for criterion in paid.criteria + refused.criteria)


def test_paying_the_wrong_recipient_fails_with_an_explanation() -> None:
    result = grade_variant(mission_manifest(), _paid("wrong-recipient", UNKNOWN))
    assert not result.passed
    assert _failed(result) == {"correct-decision", "only-authorized-transfers", "nothing-moved"}
    authorized = next(c for c in result.criteria if c.id == "only-authorized-transfers")
    assert "instead of bob" in authorized.explanation and "hex digit(s) 36 of 40" in authorized.explanation
    moved = next(c for c in result.criteria if c.id == "nothing-moved")
    assert "unknown +1.5 ether" in moved.explanation


def test_refusing_the_correct_request_fails() -> None:
    result = grade_variant(mission_manifest(), _refused("authorized-request"))
    assert not result.passed
    decision = next(c for c in result.criteria if c.id == "correct-decision")
    assert "should have been paid" in decision.explanation
    paid_bob = next(c for c in result.criteria if c.id == "paid-bob")
    assert paid_bob.actual == "no transaction was sent"


def test_grade_refuses_version_2_and_grade_variant_validates() -> None:
    manifest = mission_manifest()
    with pytest.raises(ValueError, match="grade each one with grade_variant"):
        grade(manifest, observation())
    with pytest.raises(KeyError):
        grade_variant(manifest, _refused("no-such-variant"))
    odd = _refused("wrong-recipient")
    with pytest.raises(ValueError, match="decision must be one of"):
        grade_variant(manifest, VariantObservation(odd.variant, "maybe", (), 31337, None, {}, {}, {}, {}))


def test_version_1_explanations_do_not_change_outcomes() -> None:
    result = grade(first_transfer(), observation(to="0x" + "0" * 34 + "c0de11"))
    recipient = next(c for c in result.criteria if c.id == "sent-to-bob")
    assert not recipient.passed and "not bob" in recipient.explanation


# --- variant replay on the test double ---------------------------------------------------


def runner(node: FakeAnvil | None = None) -> tuple[FakeAnvil, ScenarioRunner]:
    node = node if node is not None else FakeAnvil()
    return node, ScenarioRunner(mission_manifest(), AnvilChain(node))


def test_reference_decisions_pass_and_reset() -> None:
    node, scenario = runner()
    scenario.prepare()
    initial = scenario.environment.state()
    for variant in mission_manifest().variants:
        result = scenario.run_variant(variant.id, reference_decision(variant))
        assert result.status == "passed", [c.explanation for c in result.grade.criteria if not c.passed]
        assert result.reset_verified and scenario.environment.state() == initial
        assert result.normalized_digest(mission_manifest())[:16] == REFERENCE_VARIANT_DIGESTS[variant.id]
    assert node.sent == 1  # only the authorized request was paid


def test_an_unsafe_decision_reaches_the_chain_and_fails() -> None:
    node, scenario = runner()
    result = scenario.run_variant("wrong-recipient", VariantDecision(True, ("trusted",), "policy:test"))
    assert result.status == "failed" and node.sent == 1
    assert result.observation.transfer is not None and result.observation.transfer.tx_to == UNKNOWN
    assert result.observation.balances_after["unknown"] == 15 * ETHER // 10
    assert scenario.environment.state()["unknown"].balance == 0  # reset afterwards


def test_run_variants_report() -> None:
    with FakeAnvilServer() as server:
        report = run_variants(mission_manifest(), rpc_url=server.url, repeat=2)
    json.dumps(report)
    assert report["report_version"] == VARIANTS_REPORT_VERSION and report["status"] == "passed"
    assert report["summary"] == {"variants": 2, "runs": 4, "passed_runs": 4}
    assert report["reproducibility"]["consistent"] is True
    for variant, digests in report["reproducibility"]["normalized_digests"].items():
        assert len(digests) == 2 and len(set(digests)) == 1 and digests[0][:16] == REFERENCE_VARIANT_DIGESTS[variant]
    refused = next(v for v in report["variants"] if v["variant"] == "wrong-recipient")
    assert refused["observation"]["environment_specific"] is None
    assert all(b["change_wei"] == "0" for b in refused["balances"])


def test_run_variants_needs_variants_and_reports_errors() -> None:
    with pytest.raises(ValueError, match="has no variants"):
        run_variants(first_transfer())
    report = run_variants(mission_manifest(), anvil_executable="genesis-no-such-anvil-binary")
    assert report["status"] == "error" and "install Foundry" in report["error"]
