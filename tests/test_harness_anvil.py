"""Integration tests against a real local Anvil node.

They start a private ``anvil`` process on a free loopback port and are skipped,
with the reason shown in the test summary, when Foundry is not installed. Run
only these with ``python -m pytest -m anvil``.
"""

from __future__ import annotations

import shutil

import pytest

from genesis.harness.chain import AnvilChain, AnvilProcess, JsonRpcClient
from genesis.harness.runner import ReferenceActor, ScenarioRunner, ScriptedActor, Submission, run_scenario
from tests.harness_support import ETHER, REFERENCE_OUTCOME_DIGEST, first_transfer

pytestmark = [
    pytest.mark.anvil,
    pytest.mark.skipif(
        shutil.which("anvil") is None,
        reason="Anvil (Foundry) is not installed or not on PATH; install Foundry to run local-chain integration tests",
    ),
]


def test_first_local_transfer_passes_on_anvil() -> None:
    report = run_scenario(first_transfer())
    assert report["error"] is None, report["error"]
    assert report["status"] == "passed"
    assert str(report["environment"]["client_version"]).lower().startswith("anvil")
    assert report["environment"]["chain_id"] == 31337
    assert report["summary"]["score"] == 13
    # Node-independent: the same digest as on the in-repository test double.
    assert report["reproducibility"]["normalized_digests"] == [REFERENCE_OUTCOME_DIGEST]


def test_repeated_runs_on_anvil_agree() -> None:
    report = run_scenario(first_transfer(), repeat=3)
    assert report["status"] == "passed", report["error"]
    assert report["reproducibility"]["consistent"] is True
    assert len(set(report["reproducibility"]["normalized_digests"])) == 1
    assert all(run["reset_verified"] for run in report["runs"])


def test_reset_restores_the_initial_state_on_anvil() -> None:
    manifest = first_transfer()
    with AnvilProcess(chain_id=manifest.environment.chain_id) as node:
        assert node.url is not None
        runner = ScenarioRunner(manifest, AnvilChain(JsonRpcClient(node.url)))
        runner.prepare()
        initial = runner.environment.state()
        passed = runner.run_once(ReferenceActor())
        assert passed.status == "passed" and runner.environment.state() == initial
        failed = runner.run_once(ScriptedActor(Submission("alice", "bob", ETHER)), index=2)
        assert failed.status == "failed" and runner.environment.state() == initial
        refused = runner.run_once(ScriptedActor(Submission("alice", "bob", 20 * ETHER)), index=3)
        assert refused.status == "rejected" and runner.environment.state() == initial
