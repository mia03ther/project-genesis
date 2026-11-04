"""The validation strategies, and the content that offers them."""

from __future__ import annotations

from typing import Any

import pytest

from genesis.lab.content import MissionContentError, parse_mission
from genesis.lab.policies import POLICIES
from tests.harness_support import first_transfer
from tests.lab_support import STRATEGIES, content, manifest, raw_mission

# accept/refuse decisions for (authorized request, wrong-recipient request)
EXPECTED_DECISIONS = {
    "trust-api": (True, True),
    "preview-match": (True, True),  # both addresses shorten to 0x0000...0b0b
    "amount-and-network": (True, True),  # the recipient is never checked
    "exact-intent-match": (True, False),
    "refuse-all": (False, False),
}


@pytest.mark.parametrize("policy_id", STRATEGIES)
def test_each_strategy_decides_as_documented(policy_id: str) -> None:
    scenario = manifest()
    decisions = tuple(POLICIES[policy_id](scenario, variant.request).accepted for variant in scenario.variants)
    assert decisions == EXPECTED_DECISIONS[policy_id]


def test_only_the_exact_strategy_matches_the_scenario_expectations() -> None:
    scenario = manifest()
    expected = tuple(variant.expect == "accept" for variant in scenario.variants)
    assert [p for p, decisions in EXPECTED_DECISIONS.items() if decisions == expected] == ["exact-intent-match"]


def test_the_exact_strategy_explains_its_refusal() -> None:
    scenario = manifest()
    verdict = POLICIES["exact-intent-match"](scenario, scenario.variant("wrong-recipient").request)
    assert not verdict.accepted and "recipient does not match" in verdict.summary
    recipient = next(check for check in verdict.checks if check.field == "recipient")
    assert not recipient.passed and "hex digit(s) 36 of 40" in recipient.detail
    decision = verdict.as_decision("exact-intent-match")
    assert decision.decided_by == "policy:exact-intent-match" and decision.reasons[0] == verdict.summary


def test_the_preview_strategy_is_fooled_by_design() -> None:
    scenario = manifest()
    verdict = POLICIES["preview-match"](scenario, scenario.variant("wrong-recipient").request)
    assert verdict.accepted
    assert verdict.checks[0].detail == "0x0000...0b0b matches 0x0000...0b0b"


def test_strategies_need_an_authorization() -> None:
    request = manifest().variants[0].request
    for policy in POLICIES.values():
        with pytest.raises(ValueError, match="authorization"):
            policy(first_transfer(), request)


# --- mission content --------------------------------------------------------------------


def test_mission_content_loads() -> None:
    mission = content()
    assert mission.id == "the-wrong-recipient" and mission.featured_variant == "wrong-recipient"
    assert [c.id for c in mission.choices] == list(STRATEGIES)
    assert len(mission.hints) == 4 and len(mission.evidence) == 5
    assert mission.evidence_spec("field-comparison").requires == ("authorized-intent", "payment-request")
    assert "does not implement x402" in mission.trust_boundary.disclaimer


def _invalid(mutate: Any, message: str) -> None:
    data = raw_mission()
    mutate(data)
    with pytest.raises(MissionContentError) as caught:
        parse_mission(data, manifest())
    assert any(message in problem for problem in caught.value.errors), caught.value.errors


def test_mission_content_is_validated_against_the_scenario() -> None:
    _invalid(lambda d: d.update(scenario="other"), "is not the loaded scenario")
    _invalid(lambda d: d.update(featured_variant="nope"), "featured_variant: 'nope'")
    _invalid(lambda d: d["choices"][0].update(policy="pay-everyone"), "is not a known strategy")
    _invalid(lambda d: d["evidence"][4].update(requires=["ghost"]), "requires unknown evidence 'ghost'")
    _invalid(lambda d: d["evidence"][1].pop("variant"), "request evidence needs one of the scenario's variants")
    _invalid(lambda d: d.update(hints=d["hints"][:1]), "hints: needs at least 2 entries")
    _invalid(lambda d: d.update(title=""), "mission.title: must be a non-empty string")
    _invalid(lambda d: d.update(secret="x"), "mission.secret: is not a known field")
    _invalid(lambda d: d.update(mission_version=2), "mission_version: 2 is not supported")
