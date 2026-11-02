"""The agent interface and the rule-based policy."""

from __future__ import annotations

import json
from dataclasses import replace

import pytest

from genesis.agents import RuleBasedAgent, expected_income, workers_needed
from genesis.models import (
    Activity,
    Decision,
    MarketQuote,
    Observation,
    Occupation,
    OrderRequest,
    Resource,
    Rules,
    Side,
    SimulationConfig,
)
from genesis.simulation import build_observation, occupation_census
from genesis.world import create_world

FOOD, WOOD, STONE = Resource.FOOD, Resource.WOOD, Resource.STONE
FARMER, WOODCUTTER, MINER = Occupation.FARMER, Occupation.WOODCUTTER, Occupation.MINER


def observation(**changes: object) -> Observation:
    base = Observation(
        day=3,
        resident_id=1,
        name="Ada",
        occupation=FARMER,
        can_change_occupation=True,
        health=100,
        cash=10_000,
        inventory={FOOD: 5, WOOD: 5, STONE: 5},
        skills={FARMER: 100, WOODCUTTER: 100, MINER: 100},
        market={FOOD: MarketQuote(300), WOOD: MarketQuote(400), STONE: MarketQuote(500)},
        population=20,
        census={FARMER: 4, WOODCUTTER: 5, MINER: 11},
        money_supply=200_000,
        rules=Rules.from_config(SimulationConfig()),
    )
    return replace(base, **changes)  # type: ignore[arg-type]


def orders_by(decision: Decision) -> dict[tuple[Side, Resource], OrderRequest]:
    return {(order.side, order.resource): order for order in decision.orders}


def test_holding_exactly_the_buffer_means_no_trading() -> None:
    decision = RuleBasedAgent().decide(observation())
    assert decision == Decision(activity=Activity.WORK)


def test_buys_what_it_lacks_with_urgency_premium_but_never_its_own_product() -> None:
    obs = observation(inventory={FOOD: 0, WOOD: 0, STONE: 4})
    orders = orders_by(RuleBasedAgent().decide(obs))
    assert (Side.BUY, FOOD) not in orders  # today's work produces food
    assert orders[(Side.BUY, WOOD)] == OrderRequest(Side.BUY, WOOD, 5, 460)  # out of stock: +15 %
    assert orders[(Side.BUY, STONE)] == OrderRequest(Side.BUY, STONE, 1, 510)  # nearly full: +2 %


def test_budget_covers_todays_needs_before_buffers() -> None:
    # 900 cents buy one urgent food (345) and one urgent wood (460), not two food.
    obs = observation(occupation=MINER, cash=900, inventory={FOOD: 0, WOOD: 0, STONE: 9})
    orders = orders_by(RuleBasedAgent().decide(obs))
    assert orders[(Side.BUY, FOOD)].quantity == 1
    assert orders[(Side.BUY, WOOD)].quantity == 1
    assert sum(o.quantity * o.limit_price for o in orders.values() if o.side is Side.BUY) <= 900


def test_never_commits_more_cash_than_it_has() -> None:
    obs = observation(cash=0, inventory={FOOD: 0, WOOD: 0, STONE: 0})
    assert not [o for o in RuleBasedAgent().decide(obs).orders if o.side is Side.BUY]


def test_sells_surplus_of_its_product_at_one_day_of_output() -> None:
    obs = observation(inventory={FOOD: 12, WOOD: 5, STONE: 5})
    order = orders_by(RuleBasedAgent().decide(obs))[(Side.SELL, FOOD)]
    assert order.quantity == 5  # min(surplus 7, daily output 5)


def test_does_not_undercut_when_goods_are_cheap_relative_to_money() -> None:
    rich_town = observation(inventory={FOOD: 30, WOOD: 5, STONE: 5}, money_supply=10_000_000)
    poor_town = replace(rich_town, money_supply=100_000)
    rich_ask = orders_by(RuleBasedAgent().decide(rich_town))[(Side.SELL, FOOD)].limit_price
    poor_ask = orders_by(RuleBasedAgent().decide(poor_town))[(Side.SELL, FOOD)].limit_price
    assert rich_ask == 300
    assert poor_ask < 300


def test_rests_when_overstocked() -> None:
    assert (
        RuleBasedAgent().decide(observation(inventory={FOOD: 20, WOOD: 5, STONE: 5})).activity
        is Activity.REST
    )


def test_workers_needed_and_expected_income() -> None:
    obs = observation()
    assert workers_needed(obs, FARMER) == 4  # 20 units / 5 per farmer
    assert workers_needed(obs, MINER) == 7  # ceil(20 / 3)
    # A newcomer to woodcutting would be the 6th: (20 - 6) / 6 units each, capped at output - need.
    assert expected_income(obs, WOODCUTTER) == 233 * 400


def test_needed_workers_never_leave() -> None:
    obs = observation(day=6, census={FARMER: 4, WOODCUTTER: 5, MINER: 11}, market={
        FOOD: MarketQuote(1), WOOD: MarketQuote(400), STONE: MarketQuote(500)})  # fmt: skip
    assert RuleBasedAgent().decide(obs).new_occupation is None  # (6 + 1) % 7 == 0: a review day


def test_surplus_worker_moves_to_the_most_understaffed_occupation() -> None:
    obs = observation(day=6, census={FARMER: 8, WOODCUTTER: 4, MINER: 8})
    assert RuleBasedAgent().decide(obs).new_occupation is WOODCUTTER


def test_occupation_reviews_are_staggered_by_resident() -> None:
    obs = observation(day=5, census={FARMER: 8, WOODCUTTER: 4, MINER: 8})
    assert RuleBasedAgent().decide(obs).new_occupation is None  # (5 + 1) % 7 != 0


def test_rule_based_agent_is_deterministic() -> None:
    obs = observation(inventory={FOOD: 2, WOOD: 1, STONE: 9}, cash=777)
    assert RuleBasedAgent().decide(obs) == RuleBasedAgent().decide(obs)


# --- the interface future language-model adapters will use ---------------------


def test_decision_round_trips_through_json() -> None:
    decision = Decision(
        activity=Activity.REST,
        orders=(OrderRequest(Side.BUY, FOOD, 2, 310), OrderRequest(Side.SELL, STONE, 1, 480)),
        new_occupation=MINER,
    )
    assert Decision.from_dict(json.loads(json.dumps(decision.to_dict()))) == decision


@pytest.mark.parametrize(
    "payload",
    [
        [],
        {"activity": "dance"},
        {"orders": "buy everything"},
        {"orders": [{"side": "buy", "resource": "food", "quantity": 1.5, "limit_price": 100}]},
        {"orders": [{"side": "buy", "resource": "food", "quantity": 1}]},
        {"new_occupation": "wizard"},
        {"activity": "work", "mint_money": 10**9},
    ],
)
def test_decision_parsing_rejects_malformed_input(payload: object) -> None:
    with pytest.raises(ValueError):
        Decision.from_dict(payload)  # type: ignore[arg-type]


def test_observation_serialises_to_plain_json() -> None:
    world = create_world(seed=3)
    living = world.living()
    obs = build_observation(
        world, living[0], Rules.from_config(world.config), len(living), occupation_census(living)
    )
    payload = json.loads(json.dumps(obs.to_dict()))
    assert payload["inventory"] == {"food": 5, "wood": 5, "stone": 5}
    assert payload["rules"]["products"] == {"farmer": "food", "woodcutter": "wood", "miner": "stone"}
    assert payload["market"]["food"]["price"] == 300
