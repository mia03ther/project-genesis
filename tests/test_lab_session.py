"""The mission state machine (against the Anvil test double)."""

from __future__ import annotations

import json

import pytest

from genesis.lab.session import MissionError, Stage
from tests.lab_support import SAFE, STRATEGIES, investigate, new_session

ETHER = 10**18


def balances(state: dict) -> dict[str, str]:  # type: ignore[type-arg]
    return {row["label"]: row["balance"]["wei"] for row in state["accounts"]}


INITIAL = {"alice": str(10 * ETHER), "bob": "0", "unknown": "0"}


def test_starting_puts_the_chain_in_the_initial_state() -> None:
    _, session = new_session()
    state = session.state()
    assert state["stage"] == "investigating" and state["attempt"] == 1
    assert balances(state) == INITIAL
    assert [e["kind"] for e in state["timeline"]] == ["session-started"]
    assert state["allowed"] == {"inspect": True, "hint": True, "choose": True, "replay": False, "reset": True}
    assert next(e for e in state["evidence"] if e["id"] == "field-comparison")["locked"] is True


def test_evidence_contents() -> None:
    _, session = new_session()
    intent = session.inspect("authorized-intent")["content"]
    assert intent["recipient"]["label"] == "bob" and intent["value"]["ether"] == "1.5 ether"
    request = session.inspect("payment-request")["content"]
    assert request["pay_to"]["address"] == "0x00000000000000000000000000000000000f0b0b"
    assert "label" not in request["pay_to"]  # the request does not say whose address it is
    assert request["pay_to"]["preview"] == intent["recipient"]["preview"] == "0x0000...0b0b"
    draft = session.inspect("transaction-draft")["content"]
    assert draft["wallet_preview"] == "Send 1.5 ether to 0x0000...0b0b" and draft["gas_limit"] == 21_000
    chain = session.inspect("chain-accounts")["content"]
    unknown = next(a for a in chain["accounts"] if a["label"] == "unknown")
    assert unknown["role"] == "not in the authorization" and unknown["paid_by_request"] is True
    assert unknown["has_code"] is False and unknown["nonce"] == 0
    comparison = session.inspect("field-comparison")["content"]
    assert comparison["all_match"] is False
    assert comparison["fields"][0]["differing_positions"] == [36]
    json.dumps(comparison)


def test_locked_and_unknown_evidence() -> None:
    _, session = new_session()
    with pytest.raises(MissionError) as locked:
        session.inspect("field-comparison")
    assert locked.value.code == "evidence-locked"
    with pytest.raises(MissionError) as unknown:
        session.inspect("private-keys")
    assert unknown.value.code == "unknown-evidence" and unknown.value.status == 404


def test_inspecting_twice_records_one_event() -> None:
    _, session = new_session()
    session.inspect("authorized-intent")
    session.inspect("authorized-intent")
    assert [e["kind"] for e in session.state()["timeline"]].count("evidence-inspected") == 1


def test_hints_are_progressive_and_bounded() -> None:
    _, session = new_session()
    texts = [session.hint()["text"] for _ in range(4)]
    assert "Compare all 40 hex digits" in texts[1] and len(set(texts)) == 4
    assert session.state()["allowed"]["hint"] is False
    with pytest.raises(MissionError) as exhausted:
        session.hint()
    assert exhausted.value.code == "no-more-hints"


def test_a_strategy_needs_investigation_and_a_known_choice() -> None:
    _, session = new_session()
    with pytest.raises(MissionError) as early:
        session.choose(SAFE)
    assert early.value.code == "investigate-first"
    investigate(session)
    with pytest.raises(MissionError) as unknown:
        session.choose("pay-everything")
    assert unknown.value.code == "unknown-choice" and unknown.value.status == 422
    with pytest.raises(MissionError) as no_choice:
        session.replay()
    assert no_choice.value.code == "choose-first"


def test_the_safe_strategy_completes_the_mission() -> None:
    node, session = new_session()
    investigate(session)
    session.choose(SAFE)
    assert session.state()["allowed"]["replay"] is True
    result = session.replay()
    assert result["passed"] is True and session.stage is Stage.REPLAYED
    paid, refused = result["variants"]
    assert paid["decision"]["accepted"] and paid["transaction"]["to"]["label"] == "bob"
    assert {b["label"]: b["change"]["wei"] for b in paid["balances"]}["bob"] == str(15 * ETHER // 10)
    assert not refused["decision"]["accepted"] and refused["transaction"] is None
    assert all(b["change"]["wei"] == "0" for b in refused["balances"])
    assert all(c["passed"] and c["explanation"] for v in result["variants"] for c in v["criteria"])
    assert node.sent == 1
    assert balances(session.state()) == INITIAL  # the chain was reset after each variant
    assert "feedback" in result["choice"] and result["choice"]["feedback"].startswith("Safe.")


@pytest.mark.parametrize("strategy", [s for s in STRATEGIES if s != SAFE])
def test_every_unsafe_strategy_is_caught_by_the_judge(strategy: str) -> None:
    _, session = new_session()
    investigate(session)
    session.choose(strategy)
    result = session.replay()
    assert result["passed"] is False
    failed = {v["id"] for v in result["variants"] if v["status"] == "failed"}
    if strategy == "refuse-all":
        assert failed == {"authorized-request"}  # over-blocking: the correct payment was refused
    else:
        assert failed == {"wrong-recipient"}  # the mismatched request was paid
        wrong = next(v for v in result["variants"] if v["id"] == "wrong-recipient")
        assert wrong["transaction"]["to"]["label"] == "unknown"
        assert {b["label"]: b["change"]["wei"] for b in wrong["balances"]}["unknown"] == str(15 * ETHER // 10)
    assert balances(session.state()) == INITIAL


def test_replay_reset_replay_is_reproducible() -> None:
    _, session = new_session()
    investigate(session)
    digests = []
    for _ in range(3):
        session.choose(SAFE)
        result = session.replay()
        digests.append([v["normalized_digest"] for v in result["variants"]])
        with pytest.raises(MissionError) as again:
            session.replay()
        assert again.value.code == "reset-required"
        state = session.reset()
        assert state["stage"] == "investigating" and balances(state) == INITIAL and state["result"] is None
    assert digests[0] == digests[1] == digests[2]
    assert session.attempt == 4 and [h["passed"] for h in session.history] == [True, True, True]


def test_choosing_again_requires_a_reset_after_replay() -> None:
    _, session = new_session()
    investigate(session)
    session.choose("trust-api")
    session.choose(SAFE)  # changing your mind before the replay is fine
    session.replay()
    with pytest.raises(MissionError) as locked:
        session.choose("trust-api")
    assert locked.value.code == "reset-required"


def test_report_records_the_attempt() -> None:
    _, session = new_session()
    with pytest.raises(MissionError):
        session.report()
    investigate(session, "authorized-intent", "payment-request", "chain-accounts")
    session.hint()
    session.choose("preview-match")
    session.replay()
    report = session.report()
    json.dumps(report)
    assert report["report_format"] == "genesis.mission-report" and report["verdict"] == "failed"
    assert report["mission"]["choice"]["policy"] == "preview-match" and report["mission"]["hints_used"] == 1
    assert report["mission"]["evidence_inspected"] == ["authorized-intent", "payment-request", "chain-accounts"]
    harness = report["harness_report"]
    assert harness["report_version"] == 2 and harness["decided_by"] == "policy:preview-match"
    assert harness["status"] == "failed"


def test_timeline_tells_the_story() -> None:
    _, session = new_session()
    investigate(session)
    session.choose(SAFE)
    session.replay()
    session.reset()
    kinds = [event["kind"] for event in session.state()["timeline"]]
    assert kinds == ["session-started", "evidence-inspected", "evidence-inspected", "strategy-chosen",
                     "variant-replayed", "variant-replayed", "mission-passed", "experiment-reset"]  # fmt: skip
    assert session.state()["timeline"][-1]["attempt"] == 2
