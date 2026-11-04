"""Shared helpers for the Security Lab tests."""

from __future__ import annotations

import tomllib
from typing import Any

from genesis.harness.chain import AnvilChain
from genesis.harness.manifest import ScenarioManifest, load_manifest
from genesis.harness.runner import ScenarioRunner
from genesis.lab.content import MissionContent, load_mission
from genesis.lab.session import MissionSession
from tests.fake_anvil import FakeAnvil
from tests.harness_support import SCENARIOS

MISSION_DIR = SCENARIOS / "wrong-recipient"
STRATEGIES = ("trust-api", "preview-match", "amount-and-network", "exact-intent-match", "refuse-all")
SAFE = "exact-intent-match"


def manifest() -> ScenarioManifest:
    return load_manifest(MISSION_DIR)


def content() -> MissionContent:
    return load_mission(MISSION_DIR, manifest())


def raw_mission() -> dict[str, Any]:
    return tomllib.loads((MISSION_DIR / "mission.toml").read_text(encoding="utf-8"))


def new_session(node: FakeAnvil | None = None) -> tuple[FakeAnvil, MissionSession]:
    node = node if node is not None else FakeAnvil()
    scenario = manifest()
    session = MissionSession(scenario, load_mission(MISSION_DIR, scenario), ScenarioRunner(scenario, AnvilChain(node)),
                             {"client_version": node.client_version})  # fmt: skip
    session.start()
    return node, session


def investigate(session: MissionSession, *evidence: str) -> None:
    for evidence_id in evidence or ("authorized-intent", "payment-request"):
        session.inspect(evidence_id)
