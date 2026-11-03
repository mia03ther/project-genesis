"""The run loop, actors, submission validation and the JSON report."""

from __future__ import annotations

import json
from typing import Any

from genesis import __version__
from genesis.harness.chain import AnvilChain
from genesis.harness.runner import (
    REPORT_FORMAT,
    ReferenceActor,
    ScenarioRunner,
    ScriptedActor,
    Submission,
    TransferTask,
    run_scenario,
)
from tests.fake_anvil import FakeAnvil, FakeAnvilServer
from tests.harness_support import ETHER, GWEI, REFERENCE_OUTCOME_DIGEST, first_transfer


def runner(node: FakeAnvil | None = None) -> tuple[FakeAnvil, ScenarioRunner]:
    node = node if node is not None else FakeAnvil()
    return node, ScenarioRunner(first_transfer(), AnvilChain(node))


def test_the_task_tells_the_actor_what_to_do_but_not_how_it_is_graded() -> None:
    task = TransferTask.from_manifest(first_transfer())
    assert task.instructions == "Send 1.5 ether from alice to bob."
    assert task.requested == Submission("alice", "bob", 15 * ETHER // 10, 21_000)
    assert [a.label for a in task.accounts] == ["alice", "bob"]
    assert not hasattr(task, "grading")


def test_reference_run_passes_and_leaves_the_initial_state() -> None:
    node, scenario = runner()
    scenario.prepare()
    initial = scenario.environment.state()
    result = scenario.run_once(ReferenceActor())
    assert result.status == "passed" and result.grade is not None and result.grade.score == 13
    assert result.reset_verified and scenario.environment.state() == initial
    assert node.sent == 1


def test_a_wrong_value_is_graded_as_failed() -> None:
    _, scenario = runner()
    result = scenario.run_once(ScriptedActor(Submission("alice", "bob", ETHER)))
    assert result.status == "failed"
    assert result.grade is not None
    assert {r.id for r in result.grade.criteria if not r.passed} == {"exact-value", "bob-received-the-value"}


def test_invalid_submissions_are_rejected_without_touching_the_chain() -> None:
    node, scenario = runner()
    for submission in (
        Submission("carol", "bob", ETHER),
        Submission("alice", "dave", ETHER),
        Submission("alice", "bob", -1),
        Submission("alice", "bob", ETHER, gas_limit=1),
    ):
        result = scenario.run_once(ScriptedActor(submission))
        assert result.status == "rejected" and result.problems and result.grade is None
    assert node.sent == 0


def test_an_actor_returning_garbage_is_rejected() -> None:
    class Broken:
        name = "broken"

        def submit(self, task: TransferTask) -> Any:
            return {"from": "alice"}

    _, scenario = runner()
    result = scenario.run_once(Broken())
    assert result.status == "rejected"
    assert result.problems == ("the actor returned dict, expected a Submission",)


def test_a_transfer_the_chain_refuses_is_rejected_and_reset() -> None:
    node, scenario = runner()
    result = scenario.run_once(ScriptedActor(Submission("alice", "bob", 20 * ETHER)))
    assert result.status == "rejected"
    assert "the chain refused it" in result.problems[0] and "insufficient funds" in result.problems[0]
    assert result.reset_verified and node.sent == 0


def _run(server: FakeAnvilServer, **kwargs: Any) -> dict[str, Any]:
    return run_scenario(first_transfer(), rpc_url=server.url, **kwargs)


def test_report_structure() -> None:
    with FakeAnvilServer() as server:
        report = _run(server)
    json.dumps(report)  # machine-readable
    assert report["report_format"] == REPORT_FORMAT and report["report_version"] == 1
    assert report["genesis_version"] == __version__
    assert report["status"] == "passed" and report["error"] is None
    assert report["scenario"]["id"] == "first-local-transfer"
    assert report["scenario"]["manifest_digest"] == first_transfer().digest()
    assert report["environment"]["client_version"] == "anvil/v0.0.0-test-double"
    assert report["environment"]["managed_node"] is False
    assert report["summary"] == {
        "runs": 1,
        "passed_runs": 1,
        "score": 13,
        "max_score": 13,
        "pass_threshold": 13,
    }
    run = report["runs"][0]
    assert run["submission"] == {
        "from": "alice",
        "to": "bob",
        "value_wei": "1500000000000000000",
        "gas_limit": 21000,
    }
    assert len(run["grading"]["criteria"]) == 8
    assert run["observation"]["normalized"]["balance_changes_excluding_fee_wei"] == {
        "alice": "-1500000000000000000",
        "bob": "1500000000000000000",
    }
    assert set(run["observation"]["environment_specific"]) == set(
        report["reproducibility"]["environment_specific_fields"]
    )
    assert run["reset_verified"] is True


def test_repeated_runs_start_from_the_same_state_and_agree() -> None:
    with FakeAnvilServer() as server:
        report = _run(server, repeat=3)
        state_after = (dict(server.node.balances), dict(server.node.nonces))
    assert report["status"] == "passed" and report["summary"]["passed_runs"] == 3
    digests = report["reproducibility"]["normalized_digests"]
    assert len(digests) == 3 and len(set(digests)) == 1 and report["reproducibility"]["consistent"]
    assert all(run["reset_verified"] for run in report["runs"])
    assert state_after == ({first_transfer().account("alice").address: 10 * ETHER,
                            first_transfer().account("bob").address: 0},
                           {})  # fmt: skip


def test_reports_are_identical_across_fresh_nodes_apart_from_the_environment() -> None:
    with FakeAnvilServer() as one, FakeAnvilServer() as two:
        first, second = _run(one), _run(two)
    assert first["environment"]["rpc_url"] != second["environment"]["rpc_url"]
    first.pop("environment"), second.pop("environment")
    assert first == second


def test_normalized_digest_does_not_depend_on_gas_price() -> None:
    with (
        FakeAnvilServer(FakeAnvil(gas_price=GWEI)) as cheap,
        FakeAnvilServer(FakeAnvil(gas_price=50 * GWEI)) as dear,
    ):
        a, b = _run(cheap), _run(dear)
    assert a["status"] == b["status"] == "passed"
    assert a["reproducibility"]["normalized_digests"] == b["reproducibility"]["normalized_digests"]
    fee_a = a["runs"][0]["observation"]["environment_specific"]["fee_wei"]
    fee_b = b["runs"][0]["observation"]["environment_specific"]["fee_wei"]
    assert fee_a != fee_b


def test_wrong_value_report_fails() -> None:
    with FakeAnvilServer() as server:
        report = _run(server, actor=ScriptedActor(Submission("alice", "bob", ETHER)))
    assert report["status"] == "failed"
    assert report["runs"][0]["grading"]["failed_required"] == ["exact-value"]


def test_missing_anvil_is_reported_not_raised() -> None:
    report = run_scenario(first_transfer(), anvil_executable="genesis-no-such-anvil-binary")
    assert report["status"] == "error" and "install Foundry" in report["error"]
    assert report["runs"] == [] and report["environment"]["managed_node"] is True


def test_remote_endpoints_are_refused() -> None:
    report = run_scenario(first_transfer(), rpc_url="http://example.com:8545")
    assert report["status"] == "error" and "refusing RPC endpoint" in report["error"]


def test_reference_outcome_digest_is_pinned() -> None:
    # The same constant is checked against a real Anvil node in test_harness_anvil.py.
    with FakeAnvilServer() as server:
        report = _run(server)
    assert report["reproducibility"]["normalized_digests"] == [REFERENCE_OUTCOME_DIGEST]
