"""The Security Lab mission on a real local Anvil node (skipped when Anvil is not installed)."""

from __future__ import annotations

import shutil

import pytest

from genesis.harness.chain import AnvilChain, AnvilProcess, JsonRpcClient
from genesis.harness.runner import ScenarioRunner, run_variants
from genesis.lab.content import load_mission
from genesis.lab.session import MissionSession
from tests.harness_support import SCENARIOS
from tests.lab_support import MISSION_DIR, SAFE, investigate, manifest
from tests.test_harness_variants import REFERENCE_VARIANT_DIGESTS

pytestmark = [
    pytest.mark.anvil,
    pytest.mark.skipif(
        shutil.which("anvil") is None,
        reason="Anvil (Foundry) is not installed or not on PATH; install Foundry to run local-chain integration tests",
    ),
]


def test_reference_variants_on_anvil_match_the_pinned_digests() -> None:
    report = run_variants(manifest(), repeat=2)
    assert report["status"] == "passed", report["error"]
    for variant, digests in report["reproducibility"]["normalized_digests"].items():
        assert {d[:16] for d in digests} == {REFERENCE_VARIANT_DIGESTS[variant]}


def test_the_mission_on_anvil() -> None:
    scenario = manifest()
    with AnvilProcess(chain_id=scenario.environment.chain_id) as node:
        assert node.url is not None
        chain = AnvilChain(JsonRpcClient(node.url))
        session = MissionSession(scenario, load_mission(MISSION_DIR, scenario), ScenarioRunner(scenario, chain),
                                 {"client_version": chain.client_version()})  # fmt: skip
        session.start()
        investigate(session)
        outcomes = {}
        for strategy in ("trust-api", SAFE, "refuse-all", SAFE):
            session.choose(strategy)
            result = session.replay()
            outcomes.setdefault(strategy, []).append(result["passed"])
            wrong = next(v for v in result["variants"] if v["id"] == "wrong-recipient")
            if strategy == "trust-api":
                assert wrong["transaction"]["to"]["label"] == "unknown" and wrong["transaction"]["status"] == 1
            state = session.reset()
            assert {a["label"]: a["balance"]["wei"] for a in state["accounts"]} == {
                "alice": str(10 * 10**18), "bob": "0", "unknown": "0"}  # fmt: skip
        assert outcomes == {"trust-api": [False], SAFE: [True, True], "refuse-all": [False]}


def test_the_api_with_a_managed_anvil_node() -> None:
    pytest.importorskip("fastapi", reason="the lab API needs the optional 'lab' extra (FastAPI)")
    from fastapi.testclient import TestClient

    from genesis.lab.api import LabConfig, create_app

    with TestClient(create_app(LabConfig(scenarios_dir=SCENARIOS)), base_url="http://127.0.0.1") as client:
        health = client.get("/api/health").json()
        assert health["status"] == "ready" and health["chain"]["client_version"].startswith("anvil")
        client.post("/api/session")
        for evidence in ("authorized-intent", "payment-request", "chain-accounts", "field-comparison"):
            assert client.post(f"/api/session/evidence/{evidence}").status_code == 200
        client.post("/api/session/choice", json={"choice": SAFE})
        result = client.post("/api/session/replay").json()
        assert result["passed"] is True
        paid = result["variants"][0]["transaction"]
        assert paid["status"] == 1 and paid["gas_used"] == 21_000 and paid["to"]["label"] == "bob"
        assert client.post("/api/session/reset").json()["stage"] == "investigating"
