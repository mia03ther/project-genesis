"""The invariant checks must catch every kind of corruption they claim to cover."""

from __future__ import annotations

import copy
from dataclasses import replace

import pytest

from genesis.invariants import assert_invariants, audit_event_log, check_invariants
from genesis.models import EventKind, InvariantViolation, Resource
from genesis.world import World

FOOD = Resource.FOOD


@pytest.fixture
def world(world_100: World) -> World:
    return copy.deepcopy(world_100)


def test_a_healthy_world_passes(world: World) -> None:
    assert check_invariants(world) == []
    assert audit_event_log(world) == []
    assert_invariants(world, audit=True)


def test_negative_cash_is_detected(world: World) -> None:
    world.residents[0].cash -= world.residents[0].cash + 1
    world.residents[1].cash += 0
    problems = check_invariants(world)
    assert any("negative cash" in p for p in problems)
    assert any("currency not conserved" in p for p in problems)


def test_created_money_is_detected(world: World) -> None:
    world.residents[3].cash += 1
    assert any("currency not conserved" in p for p in check_invariants(world))


def test_moved_money_passes_the_state_check_but_not_the_audit(world: World) -> None:
    world.residents[3].cash += 50
    world.residents[4].cash -= 50  # totals still balance...
    assert check_invariants(world) == []
    problems = audit_event_log(world)  # ...but the history does not explain it
    assert any("resident 4 cash" in p for p in problems) and any("resident 5 cash" in p for p in problems)


def test_duplicated_goods_are_detected(world: World) -> None:
    world.residents[0].inventory[FOOD] += 1
    assert any("food not conserved" in p for p in check_invariants(world))


def test_negative_inventory_is_detected(world: World) -> None:
    world.residents[0].inventory[FOOD] = -1
    assert any("negative food" in p for p in check_invariants(world))


def test_tampered_trade_is_detected(world: World) -> None:
    index = next(i for i, e in enumerate(world.events) if e.kind is EventKind.TRADE)
    trade = world.events[index]
    world.events[index] = replace(trade, data={**trade.data, "value": trade.data["value"] + 1})
    problems = audit_event_log(world)
    assert any("trade value" in p for p in problems)


def test_trade_at_a_price_other_than_the_clearing_price_is_detected(world: World) -> None:
    index = next(i for i, e in enumerate(world.events) if e.kind is EventKind.TRADE)
    trade = world.events[index]
    price = trade.data["price"] + 1
    world.events[index] = replace(
        trade, data={**trade.data, "price": price, "value": trade.data["quantity"] * price}
    )
    problems = audit_event_log(world)
    assert any("clearing price" in p for p in problems)


def test_removed_event_is_detected(world: World) -> None:
    del world.events[len(world.events) // 2]
    assert any("sequence" in p for p in check_invariants(world) + audit_event_log(world))


def test_unrecorded_production_is_detected(world: World) -> None:
    world.ledger.produced[FOOD] += 3
    world.residents[0].inventory[FOOD] += 3
    assert check_invariants(world) == []  # the ledger and the state agree...
    assert any("ledger produced food" in p for p in audit_event_log(world))  # ...the log does not


def test_dead_resident_with_health_is_detected(world: World) -> None:
    world.residents[0].alive = False
    assert any("alive=False" in p for p in check_invariants(world))


def test_assert_invariants_raises(world: World) -> None:
    world.residents[0].cash += 1
    with pytest.raises(InvariantViolation, match="currency not conserved"):
        assert_invariants(world)
