"""The deterministic judge."""

from __future__ import annotations

from genesis.harness.grading import EVALUATORS, digest, grade
from genesis.harness.manifest import CHECKS, parse_manifest
from tests.harness_support import ETHER, GWEI, first_transfer, manifest_with, observation, raw_manifest

OTHER = "0x00000000000000000000000000000000000c0de1"


def results(manifest_grade: object) -> dict[str, bool]:
    return {r.id: r.passed for r in manifest_grade.criteria}  # type: ignore[attr-defined]


def test_correct_transfer_passes_every_criterion() -> None:
    result = grade(first_transfer(), observation())
    assert all(results(result).values())
    assert (result.score, result.max_score, result.passed) == (13, 13, True)
    assert result.failed_required == ()


def test_incorrect_expected_values_fail_the_right_criteria() -> None:
    # The scenario now expects 2 ether, but the chain shows a 1.5 ether transfer.
    data = raw_manifest()
    data["transaction"]["value"] = "2 ether"
    next(c for c in data["grading"]["criteria"] if c["id"] == "bob-received-the-value")["expect"] = "2 ether"
    result = grade(parse_manifest(data), observation())
    failed = {cid for cid, ok in results(result).items() if not ok}
    assert failed == {"exact-value", "bob-received-the-value"}
    assert result.passed is False
    assert result.failed_required == ("exact-value",)
    value = next(r for r in result.criteria if r.id == "exact-value")
    assert value.expected == "2000000000000000000 wei (2 ether)"
    assert value.actual == "1500000000000000000 wei (1.5 ether)"
    assert value.awarded == 0


def test_a_learner_sending_the_wrong_amount_fails() -> None:
    result = grade(first_transfer(), observation(value=ETHER))
    assert not results(result)["exact-value"] and not results(result)["bob-received-the-value"]
    assert results(result)["alice-paid-value-and-fee"]  # the accounting of what did happen is still exact
    assert result.passed is False


def test_wrong_recipient_fails_a_required_criterion() -> None:
    result = grade(first_transfer(), observation(to=OTHER))
    recipient = next(r for r in result.criteria if r.id == "sent-to-bob")
    assert not recipient.passed and recipient.actual.endswith("(not a scenario account)")
    assert "sent-to-bob" in result.failed_required
    assert result.passed is False


def test_reverted_transaction_fails() -> None:
    result = grade(first_transfer(), observation(status=0))
    assert not results(result)["transaction-succeeded"]
    assert "transaction-succeeded" in result.failed_required
    assert not results(result)["bob-received-the-value"]


def test_fee_accounting_is_exact_to_the_wei() -> None:
    result = grade(first_transfer(), observation(sender_adjust=-1))
    failed = {cid for cid, ok in results(result).items() if not ok}
    assert failed == {"alice-paid-value-and-fee"}
    assert result.score == 11 and result.passed is False  # every point is needed


def test_partial_credit_passes_when_the_threshold_allows_it() -> None:
    lenient = manifest_with(grading={"pass_threshold": 12})
    result = grade(lenient, observation(gas_used=21_001))
    assert not results(result)["plain-transfer-gas"]
    assert result.score == 12 and result.passed is True  # the gas criterion is not required


def test_grading_is_deterministic() -> None:
    manifest, seen = first_transfer(), observation(value=ETHER)
    assert grade(manifest, seen) == grade(manifest, seen)
    assert grade(manifest, seen).to_dict() == grade(manifest, seen).to_dict()


def test_normalized_view_ignores_environment_specific_values() -> None:
    manifest = first_transfer()
    one = observation(gas_price=GWEI, tx_hash="0x" + "11" * 32, block_hash="0x" + "22" * 32, block_number=1)
    two = observation(
        gas_price=7 * GWEI, tx_hash="0x" + "33" * 32, block_hash="0x" + "44" * 32, block_number=9
    )
    assert one.normalized(manifest) == two.normalized(manifest)
    assert digest(one.normalized(manifest)) == digest(two.normalized(manifest))
    assert one.environment_specific() != two.environment_specific()
    assert one.normalized(manifest)["balance_changes_excluding_fee_wei"] == {
        "alice": str(-3 * ETHER // 2),
        "bob": str(3 * ETHER // 2),
    }


def test_every_check_has_exactly_one_evaluator() -> None:
    assert set(EVALUATORS) == set(CHECKS)
