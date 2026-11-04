"""The Security Lab HTTP API, driven with FastAPI's test client against the Anvil test double."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest

pytest.importorskip("fastapi", reason="the lab API needs the optional 'lab' extra (FastAPI)")

from fastapi.testclient import TestClient

from genesis.harness.chain import AnvilChain
from genesis.lab.api import LabConfig, create_app
from tests.fake_anvil import FakeAnvil
from tests.harness_support import SCENARIOS

BASE = "http://127.0.0.1"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = create_app(LabConfig(scenarios_dir=SCENARIOS), chain=AnvilChain(FakeAnvil()))
    with TestClient(app, base_url=BASE) as test_client:
        yield test_client


def started(client: TestClient) -> TestClient:
    assert client.post("/api/session").status_code == 200
    for evidence in ("authorized-intent", "payment-request"):
        assert client.post(f"/api/session/evidence/{evidence}").status_code == 200
    return client


def test_health_and_mission(client: TestClient) -> None:
    assert client.get("/api/health").json()["status"] == "ready"
    mission = client.get("/api/mission").json()
    assert mission["title"] == "The Wrong Recipient"
    assert len(mission["choices"]) == 5 and mission["hints_total"] == 4
    assert all(set(choice) == {"id", "label", "detail"} for choice in mission["choices"])  # no answer leaked
    assert "does not implement x402" in mission["trust_boundary"]["disclaimer"]
    assert mission["scenario"]["variants"][1]["id"] == "wrong-recipient"


def test_full_mission_through_the_api(client: TestClient) -> None:
    assert client.get("/api/session").status_code == 404
    started(client)
    comparison = client.post("/api/session/evidence/field-comparison").json()
    assert comparison["content"]["all_match"] is False
    hint = client.post("/api/session/hints").json()
    assert hint == {"index": 1, "total": 4, "text": hint["text"]}
    state = client.post("/api/session/choice", json={"choice": "exact-intent-match"}).json()
    assert state["stage"] == "diagnosed" and state["allowed"]["replay"] is True
    result = client.post("/api/session/replay").json()
    assert result["passed"] is True and [v["status"] for v in result["variants"]] == ["passed", "passed"]
    report = client.get("/api/session/report")
    assert report.status_code == 200 and report.json()["verdict"] == "passed"
    state = client.post("/api/session/reset").json()
    assert state["stage"] == "investigating" and state["attempt"] == 2 and state["result"] is None
    assert state["history"] == [{"attempt": 1, "choice": "exact-intent-match",
                                 "label": "Validate every field against the authorization", "passed": True}]  # fmt: skip


def test_unsafe_strategy_is_graded_as_failed(client: TestClient) -> None:
    started(client)
    client.post("/api/session/choice", json={"choice": "trust-api"})
    result = client.post("/api/session/replay").json()
    assert result["passed"] is False
    wrong = result["variants"][1]
    assert wrong["status"] == "failed" and wrong["transaction"]["to"]["label"] == "unknown"
    assert result["choice"]["feedback"].startswith("Unsafe.")


@pytest.mark.parametrize(
    ("body", "status"),
    [
        ({"choice": "Pay Everyone"}, 422),  # not an id
        ({"choice": "x" * 65}, 422),  # too long
        ({"choice": "pay-everyone"}, 422),  # not a known strategy
        ({"choice": "trust-api", "to": "0x" + "12" * 20}, 422),  # no extra fields
        ({}, 422),
    ],
)
def test_choices_are_validated(client: TestClient, body: dict, status: int) -> None:  # type: ignore[type-arg]
    started(client)
    response = client.post("/api/session/choice", json=body)
    assert response.status_code == status


def test_evidence_ids_are_validated(client: TestClient) -> None:
    client.post("/api/session")
    assert client.post("/api/session/evidence/..%2Fsecrets").status_code in (404, 422)
    assert client.post("/api/session/evidence/UPPER").status_code == 422
    assert client.post("/api/session/evidence/private-keys").json()["error"]["code"] == "unknown-evidence"
    assert client.post("/api/session/evidence/field-comparison").json()["error"]["code"] == "evidence-locked"


def test_state_errors_are_explicit(client: TestClient) -> None:
    assert client.post("/api/session/replay").json()["error"]["code"] == "no-session"
    started(client)
    assert client.post("/api/session/replay").json()["error"]["code"] == "choose-first"
    assert client.get("/api/session/report").status_code == 404


def test_there_is_no_raw_chain_access(client: TestClient) -> None:
    for path in ("/api/rpc", "/api/chain", "/api/transaction", "/api/send", "/api/exec"):
        assert client.post(path, json={"method": "eth_sendTransaction"}).status_code in (404, 405)
    assert client.get("/api/session/replay").status_code == 405  # actions are POST only
    paths = set(client.get("/api/openapi.json").json()["paths"])
    assert paths == {
        "/api/health", "/api/mission", "/api/session", "/api/session/evidence/{evidence_id}", "/api/session/hints",
        "/api/session/choice", "/api/session/replay", "/api/session/reset", "/api/session/report",
    }  # fmt: skip


def test_foreign_hosts_are_refused_and_headers_are_strict(client: TestClient) -> None:
    assert client.get("/api/health", headers={"host": "attacker.example"}).status_code == 400
    response = client.get("/api/health")
    assert "default-src 'self'" in response.headers["content-security-policy"]
    assert response.headers["x-frame-options"] == "DENY" and response.headers["cache-control"] == "no-store"


def test_missing_anvil_gives_a_clear_503() -> None:
    config = LabConfig(scenarios_dir=SCENARIOS, anvil_executable="genesis-no-such-anvil-binary")
    with TestClient(create_app(config), base_url=BASE) as test_client:
        health = test_client.get("/api/health")
        assert health.status_code == 503 and "install Foundry" in health.json()["error"]
        failure = test_client.post("/api/session")
        assert failure.status_code == 503 and failure.json()["error"]["code"] == "chain-unavailable"
        assert test_client.get("/api/mission").status_code == 200  # the briefing still loads


def test_remote_rpc_urls_are_refused() -> None:
    config = LabConfig(scenarios_dir=SCENARIOS, rpc_url="http://203.0.113.10:8545")
    with TestClient(create_app(config), base_url=BASE) as test_client:
        assert "refusing RPC endpoint" in test_client.get("/api/health").json()["error"]


def test_built_frontend_is_served(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<!doctype html><title>lab</title>", encoding="utf-8")
    app = create_app(LabConfig(scenarios_dir=SCENARIOS, static_dir=tmp_path), chain=AnvilChain(FakeAnvil()))
    with TestClient(app, base_url=BASE) as test_client:
        page = test_client.get("/")
        assert page.status_code == 200 and "<title>lab</title>" in page.text
        assert "script-src 'self'" in page.headers["content-security-policy"]
        assert test_client.get("/api/health").json()["status"] == "ready"
