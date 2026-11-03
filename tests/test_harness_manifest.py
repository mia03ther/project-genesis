"""Scenario manifest schema, loading and validation."""

from __future__ import annotations

import dataclasses
import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest

from genesis.harness.manifest import (
    CHECKS,
    ManifestError,
    find_manifests,
    load_manifest,
    parse_manifest,
)
from tests.harness_support import ALICE, ETHER, FIRST_TRANSFER, SCENARIOS, first_transfer, raw_manifest


def test_bundled_scenario_is_valid() -> None:
    manifest = first_transfer()
    assert manifest.manifest_version == 1
    assert manifest.scenario.id == "first-local-transfer"
    assert manifest.scenario.version == "1.0.0"
    assert manifest.scenario.title == "First Local Blockchain Transfer"
    assert len(manifest.scenario.learning_objectives) == 5
    assert manifest.environment.kind == "anvil" and manifest.environment.chain_id == 31337
    assert [(a.label, a.balance) for a in manifest.accounts] == [("alice", 10 * ETHER), ("bob", 0)]
    assert manifest.account("alice").address == ALICE
    transfer = manifest.transaction
    assert (transfer.sender, transfer.recipient, transfer.value, transfer.gas_limit) == (
        "alice",
        "bob",
        15 * ETHER // 10,
        21_000,
    )
    assert manifest.grading.max_score == manifest.grading.pass_threshold == 13
    assert {c.check for c in manifest.grading.criteria} == set(CHECKS)  # the scenario exercises every check
    assert manifest.metadata["created"] == "2026-11-02"


def test_digest_is_stable_and_independent_of_file_format(tmp_path: Path) -> None:
    manifest = first_transfer()
    assert manifest.digest() == first_transfer().digest()
    data = raw_manifest()
    data["metadata"]["created"] = "2026-11-02"  # JSON has no date type
    json_path = tmp_path / "scenario.json"
    json_path.write_text(json.dumps(data, indent=4), encoding="utf-8")
    from_json = load_manifest(json_path)
    assert from_json == manifest
    assert from_json.digest() == manifest.digest()


def test_digest_changes_with_content() -> None:
    data = raw_manifest()
    data["transaction"]["value"] = "1.25 ether"
    assert parse_manifest(data).digest() != first_transfer().digest()


def test_manifest_is_immutable() -> None:
    manifest = first_transfer()
    with pytest.raises(dataclasses.FrozenInstanceError):
        manifest.scenario.title = "changed"  # type: ignore[misc]
    with pytest.raises(TypeError):
        manifest.metadata["notes"] = "changed"  # type: ignore[index]


def _criterion(data: dict[str, Any], criterion_id: str) -> dict[str, Any]:
    return next(c for c in data["grading"]["criteria"] if c["id"] == criterion_id)


Mutation = Callable[[dict[str, Any]], None]

INVALID: list[tuple[str, Mutation, str]] = [
    ("missing title", lambda d: d["scenario"].pop("title"), "scenario.title: is required"),
    ("typo in a field", lambda d: d["scenario"].update(lerning_objectives=["x"]),
     "scenario.lerning_objectives: is not a known field"),
    ("unknown section", lambda d: d.update(wallets={}), "manifest.wallets: is not a known field"),
    ("bad id", lambda d: d["scenario"].update(id="First Transfer"), "scenario.id: 'First Transfer' does not have"),
    ("bad version", lambda d: d["scenario"].update(version="1.0"), "scenario.version: '1.0' does not have"),
    ("no objectives", lambda d: d["scenario"].update(learning_objectives=[]), "learning_objectives: must not be empty"),
    ("bad difficulty", lambda d: d["scenario"].update(difficulty="expert"), "scenario.difficulty: must be one of"),
    ("bad minutes", lambda d: d["scenario"].update(estimated_minutes=0), "estimated_minutes: must be between 1"),
    ("public network", lambda d: d["environment"].update(kind="monad-testnet"),
     "environment.kind: 'monad-testnet' is not supported"),
    ("bad chain id", lambda d: d["environment"].update(chain_id="31337"), "environment.chain_id: must be an integer"),
    ("one account", lambda d: d.update(accounts=d["accounts"][:1]), "accounts: must list 2 to 16 accounts"),
    ("bad address", lambda d: d["accounts"][1].update(address="0x123"), "accounts[1].address: '0x123' does not have"),
    ("duplicate label", lambda d: d["accounts"][1].update(label="alice"), "accounts[1].label: duplicate label 'alice'"),
    ("duplicate address", lambda d: d["accounts"][1].update(address=ALICE), "accounts[1].address: duplicate address"),
    ("precompile address", lambda d: d["accounts"][1].update(address="0x" + "0" * 39 + "1"),
     "accounts[1].address: is in the reserved low address range"),
    ("bad balance", lambda d: d["accounts"][0].update(balance="lots"), "accounts[0].balance: amount 'lots'"),
    ("fractional wei", lambda d: d["accounts"][0].update(balance="1.5 wei"), "is not a whole number of wei"),
    ("unknown recipient", lambda d: d["transaction"].update(to="carol"),
     "transaction.to: 'carol' is not one of the scenario's accounts"),
    ("self transfer", lambda d: d["transaction"].update(to="alice"), "transaction.to: must differ"),
    ("value exceeds balance", lambda d: d["transaction"].update(value="10 ether"),
     "transaction.value: the sender's starting balance must exceed the value"),
    ("gas too low", lambda d: d["transaction"].update(gas_limit=20_000), "transaction.gas_limit: must be between 21000"),
    ("unknown check", lambda d: _criterion(d, "sent-by-alice").update(check="vibes"), "unknown check 'vibes'"),
    ("missing account", lambda d: _criterion(d, "bob-received-the-value").pop("account"),
     "account: is required by check 'final_balance'"),
    ("unused account", lambda d: _criterion(d, "sent-by-alice").update(account="bob"),
     "account: is not used by check 'sender'"),
    ("unknown account", lambda d: _criterion(d, "bob-received-the-value").update(account="carol"),
     "account: 'carol' is not one of the scenario's accounts"),
    ("missing expect", lambda d: _criterion(d, "plain-transfer-gas").pop("expect"),
     "expect: is required by check 'gas_used'"),
    ("bad status", lambda d: _criterion(d, "transaction-succeeded").update(expect="maybe"),
     "expect: must be one of success, reverted"),
    ("duplicate criterion", lambda d: _criterion(d, "sent-by-alice").update(id="sent-to-bob"),
     "duplicate criterion id 'sent-to-bob'"),
    ("bad points", lambda d: _criterion(d, "sent-by-alice").update(points=-1), "points: must be between 0 and 100"),
    ("bad required flag", lambda d: _criterion(d, "sent-by-alice").update(required="yes"), "required: must be true or false"),
    ("threshold too high", lambda d: d["grading"].update(pass_threshold=99), "grading.pass_threshold: must be between 0 and 13"),
    ("no criteria", lambda d: d["grading"].update(criteria=[]), "grading.criteria: must list 1 to 32 criteria"),
    ("unknown metadata", lambda d: d["metadata"].update(website="x"), "metadata.website: is not a known field"),
    ("bad date", lambda d: d["metadata"].update(created="yesterday"), "metadata.created: must be a date"),
]  # fmt: skip


@pytest.mark.parametrize(
    ("mutate", "message"), [case[1:] for case in INVALID], ids=[case[0] for case in INVALID]
)
def test_invalid_manifests_are_rejected_with_a_located_message(mutate: Mutation, message: str) -> None:
    data = raw_manifest()
    mutate(data)
    with pytest.raises(ManifestError) as caught:
        parse_manifest(data, source="test.toml")
    assert any(message in problem for problem in caught.value.errors), caught.value.errors
    assert str(caught.value).startswith("test.toml: ")


def test_unsupported_manifest_version_is_refused_first() -> None:
    data = raw_manifest()
    data["manifest_version"] = 2
    with pytest.raises(ManifestError, match="manifest_version: 2 is not supported; this build reads 1"):
        parse_manifest(data)


def test_every_problem_is_reported_at_once() -> None:
    data = raw_manifest()
    data["scenario"]["id"] = "Bad Id"
    data["accounts"][1]["address"] = "nope"
    data["transaction"]["to"] = "carol"
    with pytest.raises(ManifestError) as caught:
        parse_manifest(data)
    assert len(caught.value.errors) >= 3


def test_defaults_are_made_explicit() -> None:
    data = raw_manifest()
    nonce = _criterion(data, "alice-nonce-increased")
    del nonce["account"], nonce["expect"]
    status = _criterion(data, "transaction-succeeded")
    del status["expect"], status["required"], status["points"]
    del data["grading"]["pass_threshold"], data["transaction"]["gas_limit"]
    manifest = parse_manifest(data)
    by_id = {c.id: c for c in manifest.grading.criteria}
    assert (by_id["alice-nonce-increased"].account, by_id["alice-nonce-increased"].expect) == ("alice", 1)
    assert (by_id["transaction-succeeded"].expect, by_id["transaction-succeeded"].required) == (
        "success",
        False,
    )
    assert by_id["transaction-succeeded"].points == 1
    assert manifest.grading.pass_threshold == manifest.grading.max_score
    assert manifest.transaction.gas_limit == 21_000


def test_addresses_are_normalised_to_lower_case() -> None:
    data = raw_manifest()
    data["accounts"][0]["address"] = ALICE.upper().replace("0X", "0x")
    assert parse_manifest(data).account("alice").address == ALICE


@pytest.mark.parametrize("payload", [[], "manifest", 42, None])
def test_non_table_manifests_are_rejected(payload: object) -> None:
    with pytest.raises(ManifestError):
        parse_manifest(payload)


def test_unparseable_files_are_reported(tmp_path: Path) -> None:
    bad_toml = tmp_path / "scenario.toml"
    bad_toml.write_text("manifest_version = = 1\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="cannot parse TOML"):
        load_manifest(bad_toml)
    bad_json = tmp_path / "scenario.json"
    bad_json.write_text("{not json", encoding="utf-8")
    with pytest.raises(ManifestError, match="cannot parse JSON"):
        load_manifest(bad_json)
    other = tmp_path / "scenario.yaml"
    other.write_text("x: 1\n", encoding="utf-8")
    with pytest.raises(ManifestError, match="unsupported file type"):
        load_manifest(other)
    with pytest.raises(FileNotFoundError):
        load_manifest(tmp_path / "missing.toml")


def test_a_scenario_directory_resolves_to_its_manifest() -> None:
    assert load_manifest(FIRST_TRANSFER).source == str(FIRST_TRANSFER / "scenario.toml")


def test_find_manifests_lists_the_bundled_scenario() -> None:
    assert FIRST_TRANSFER / "scenario.toml" in find_manifests(SCENARIOS)
