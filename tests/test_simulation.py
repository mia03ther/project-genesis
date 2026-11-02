"""The daily loop: stability, reproducibility, accounting and engine authority."""

from __future__ import annotations

import random
from collections import Counter
from dataclasses import replace

import pytest

from genesis.agents import RuleBasedAgent
from genesis.invariants import assert_invariants, audit_event_log, check_invariants
from genesis.models import (
    OCCUPATIONS,
    RESOURCES,
    Activity,
    Decision,
    EventKind,
    Observation,
    Occupation,
    OrderRequest,
    Resource,
    Side,
    SimulationConfig,
)
from genesis.simulation import Simulation
from genesis.world import World, create_world
from tests.conftest import run_world

# --- stability -----------------------------------------------------------------


def test_default_world_runs_100_days_with_invariants_checked_daily(world_100: World) -> None:
    assert world_100.day == 100
    assert len(world_100.stats) == 100
    assert audit_event_log(world_100) == []
    assert all(r.cash >= 0 and min(r.inventory.values()) >= 0 for r in world_100.residents)


@pytest.mark.parametrize("seed", [1, 2, 3, 4, 5])
def test_long_runs_stay_consistent(seed: int) -> None:
    world = run_world(365, seed=seed)  # invariants are asserted after every day
    assert_invariants(world, audit=True)
    assert world.stats[-1].population > 0


def test_default_economy_is_sustainable_for_100_days(world_100: World) -> None:
    # Not an invariant, but a regression guard on the default economy.
    assert world_100.stats[-1].population == 20
    assert min(s.mean_health for s in world_100.stats) > 90
    assert all(sum(s.trade_volume.values()) > 0 for s in world_100.stats[1:])


def test_money_supply_is_constant_every_day(world_100: World) -> None:
    assert {s.money_supply for s in world_100.stats} == {world_100.ledger.money_supply}
    assert world_100.ledger.money_supply == 20 * SimulationConfig().initial_cash


def test_production_and_consumption_are_accounted_three_ways(world_100: World) -> None:
    produced, consumed = Counter(), Counter()
    for event in world_100.events:
        if event.kind is EventKind.PRODUCTION:
            produced[event.data["resource"]] += event.data["quantity"]
        elif event.kind is EventKind.CONSUMPTION:
            consumed.update(event.data["consumed"])
    for resource in RESOURCES:
        from_stats = sum(s.production[resource] for s in world_100.stats)
        assert produced[str(resource)] == world_100.ledger.produced[resource] == from_stats
        from_stats = sum(s.consumption[resource] for s in world_100.stats)
        assert consumed[str(resource)] == world_100.ledger.consumed[resource] == from_stats
        assert world_100.holdings()[resource] == world_100.ledger.expected_holdings(resource)


def test_trades_conserve_money_and_goods_day_by_day(world_100: World) -> None:
    for day in range(1, 101):
        trades = [e for e in world_100.events if e.day == day and e.kind is EventKind.TRADE]
        assert all(e.resident_id != e.counterparty_id for e in trades)
        assert all(e.data["value"] == e.data["quantity"] * e.data["price"] for e in trades)
        stats = world_100.stats[day - 1]
        for resource in RESOURCES:
            units = sum(e.data["quantity"] for e in trades if e.data["resource"] == resource)
            assert units == stats.trade_volume[resource]


# --- reproducibility ---------------------------------------------------------------


def test_same_seed_gives_identical_history(world_100: World) -> None:
    again = run_world(100, seed=42)
    assert again.state_digest() == world_100.state_digest()
    assert again.events == world_100.events


def test_different_seeds_give_different_histories(world_100: World) -> None:
    assert run_world(100, seed=43).state_digest() != world_100.state_digest()


#: Digest of the default world (seed 42) after 100 days, identical on Python 3.12-3.14.
#: It pins the exact behaviour of the engine and the rule-based policy across machines.
#: Change it only together with a deliberate change to the simulation rules (and the README).
REFERENCE_DIGEST = "8ed4e8d7dd86fafce0ec09064a239b599d0eb596f4588d69b249cbbd1ad201c6"


def test_reference_run_is_bit_for_bit_reproducible(world_100: World) -> None:
    assert world_100.state_digest() == REFERENCE_DIGEST


def test_creation_is_reproducible_and_varied() -> None:
    assert create_world(seed=9).state_digest() == create_world(seed=9).state_digest()
    names = [r.name for r in create_world(seed=9).residents]
    assert len(set(names)) == len(names) == 20


def test_large_populations_get_unique_names() -> None:
    world = create_world(SimulationConfig(num_residents=85), seed=1)
    assert len({r.name for r in world.residents}) == 85


# --- engine authority --------------------------------------------------------------


class ScriptedAgent:
    """Returns the same decision every day."""

    def __init__(self, decision: object) -> None:
        self.decision = decision

    def decide(self, observation: Observation) -> object:
        return self.decision


class FailingAgent:
    def decide(self, observation: Observation) -> Decision:
        raise RuntimeError("model unavailable")


def world_with_policy(policy: str, seed: int = 1, **config: object) -> World:
    return create_world(SimulationConfig(**config), seed=seed, policy=policy)  # type: ignore[arg-type]


def kinds(world: World, kind: EventKind) -> list:
    return [e for e in world.events if e.kind is kind]


def test_agent_exceptions_are_logged_and_the_world_continues() -> None:
    world = world_with_policy("flaky")
    Simulation(world, {"flaky": FailingAgent()}).run(5)
    errors = kinds(world, EventKind.AGENT_ERROR)
    assert len(errors) == 5 * 20
    assert errors[0].data["error"] == "RuntimeError: model unavailable"
    assert len(kinds(world, EventKind.PRODUCTION)) == 5 * 20  # the default decision is to work


def test_malformed_return_values_are_logged_and_replaced() -> None:
    world = world_with_policy("bad")
    Simulation(world, {"bad": ScriptedAgent({"activity": "work"})}).run(2)
    assert "expected Decision" in kinds(world, EventKind.AGENT_ERROR)[0].data["error"]


def test_engine_rejects_overspending_and_overselling() -> None:
    greedy = Decision(
        orders=(
            OrderRequest(Side.BUY, Resource.FOOD, 1_000, 1_000_000),  # far beyond any cash
            OrderRequest(Side.SELL, Resource.STONE, 999, 1),  # far beyond any inventory
        )
    )
    world = world_with_policy("greedy")
    Simulation(world, {"greedy": ScriptedAgent(greedy)}).run(5)
    reasons = Counter(e.data["reason"] for e in kinds(world, EventKind.ORDER_REJECTED))
    assert reasons == {"insufficient_funds": 100, "insufficient_inventory": 100}
    assert kinds(world, EventKind.TRADE) == []
    assert_invariants(world, audit=True)


def test_invalid_activity_and_occupation_are_rejected() -> None:
    world = world_with_policy("odd")
    odd = Decision(activity="party", new_occupation="astronaut")  # type: ignore[arg-type]
    Simulation(world, {"odd": ScriptedAgent(odd)}).run(1)
    reasons = Counter(e.data["reason"] for e in kinds(world, EventKind.ACTION_REJECTED))
    assert reasons == {"invalid_activity": 20, "invalid_occupation": 20}
    assert len(kinds(world, EventKind.PRODUCTION)) == 20  # invalid activity falls back to work


def test_occupation_changes_respect_the_cooldown() -> None:
    world = world_with_policy("restless", occupation_cooldown_days=3)

    class Restless:
        """Trades like the rule-based agent but asks for a new occupation every day."""

        def decide(self, observation: Observation) -> Decision:
            others = [occ for occ in OCCUPATIONS if occ is not observation.occupation]
            return replace(RuleBasedAgent().decide(observation), new_occupation=others[observation.day % 2])

    Simulation(world, {"restless": Restless()}).run(7)
    changes = Counter(e.resident_id for e in kinds(world, EventKind.OCCUPATION_CHANGED))
    assert changes == {resident.id: 3 for resident in world.residents}  # days 1, 4 and 7
    rejected = Counter(e.data["reason"] for e in kinds(world, EventKind.ACTION_REJECTED))
    assert rejected == {"occupation_cooldown": 4 * 20}


class ChaosAgent:
    """Proposes random, frequently invalid decisions (deterministically, from the observation)."""

    def decide(self, observation: Observation) -> Decision:
        rng = random.Random(observation.day * 1_000 + observation.resident_id)
        values: list[object] = [0, -1, 1, 2, 5, 50, 10**9, 2.5, True, None, "7"]
        orders = tuple(
            OrderRequest(
                rng.choice([Side.BUY, Side.SELL, "steal"]),  # type: ignore[arg-type]
                rng.choice([*RESOURCES, "gold"]),  # type: ignore[arg-type]
                rng.choice(values),  # type: ignore[arg-type]
                rng.choice([*values, 300, 450, 800]),  # type: ignore[arg-type]
            )
            for _ in range(rng.randint(0, 14))
        )
        return Decision(
            activity=rng.choice([Activity.WORK, Activity.REST, "nap"]),  # type: ignore[arg-type]
            orders=orders,
            new_occupation=rng.choice([None, None, None, *OCCUPATIONS, "pirate"]),  # type: ignore[arg-type]
        )


def test_chaotic_agents_cannot_break_invariants() -> None:
    world = world_with_policy("chaos", seed=5)
    Simulation(world, {"chaos": ChaosAgent()}).run(60)  # invariants are checked every day
    assert_invariants(world, audit=True)
    assert kinds(world, EventKind.ORDER_REJECTED) and kinds(world, EventKind.ACTION_REJECTED)
    assert kinds(world, EventKind.TRADE)  # valid orders still trade


def test_mixed_policies_share_one_world() -> None:
    world = create_world(seed=2)
    for resident in world.residents[::2]:
        resident.policy = "chaos"
    Simulation(world, {"rule_based": RuleBasedAgent(), "chaos": ChaosAgent()}).run(30)
    assert_invariants(world, audit=True)


def test_unknown_policy_is_refused_up_front() -> None:
    with pytest.raises(ValueError, match="no agent registered"):
        Simulation(world_with_policy("ghost"))


def test_agents_cannot_mutate_the_world_through_observations() -> None:
    class Vandal:
        def decide(self, observation: Observation) -> Decision:
            observation.inventory[Resource.FOOD] = 10**6
            observation.market[Resource.FOOD].price = 1
            observation.census[Occupation.FARMER] = 0
            with pytest.raises(TypeError):
                observation.rules.daily_needs[Resource.FOOD] = 0  # type: ignore[index]
            return Decision()

    world = world_with_policy("vandal")
    Simulation(world, {"vandal": Vandal()}).run(3)
    assert world.market[Resource.FOOD].price == 300  # no orders were placed, so no price moved
    assert max(r.inventory[Resource.FOOD] for r in world.residents) < 1_000
    assert world.config.daily_needs[Resource.FOOD] == 1
    assert check_invariants(world) == []


# --- life and death ------------------------------------------------------------------


def test_the_dead_stop_acting_and_their_estates_are_frozen() -> None:
    # No money and no stock: only farmers can feed themselves, everyone else starves.
    world = create_world(
        SimulationConfig(initial_cash=0, initial_inventory={"food": 0, "wood": 0, "stone": 0}), seed=4
    )
    Simulation(world).run(30)
    dead = [r for r in world.residents if not r.alive]
    assert dead and all(r.health == 0 and r.died_on is not None for r in dead)
    for resident in dead:
        died = [e for e in world.events if e.kind is EventKind.RESIDENT_DIED and e.resident_id == resident.id]
        assert len(died) == 1 and died[0].day == resident.died_on
        assert died[0].data["estate_cash"] == resident.cash
        later = [
            e for e in world.events
            if e.day > resident.died_on and resident.id in (e.resident_id, e.counterparty_id)
        ]  # fmt: skip
        assert later == []
    assert world.stats[-1].population == len(world.living())
    assert_invariants(world, audit=True)


def test_an_empty_world_keeps_running() -> None:
    world = create_world(
        SimulationConfig(initial_cash=0, initial_inventory={"food": 0, "wood": 0, "stone": 0},
                         unmet_need_penalty={"food": 100, "wood": 0, "stone": 0}, base_output={
                             "farmer": 0, "woodcutter": 0, "miner": 0}),
        seed=1,
    )  # fmt: skip
    Simulation(world).run(5)
    assert world.stats[-1].population == 0
    assert check_invariants(world) == []


def test_resting_skips_production_and_adds_recovery() -> None:
    world = world_with_policy("sleepy")
    for resident in world.residents:
        resident.health = 80
    Simulation(world, {"sleepy": ScriptedAgent(Decision(activity=Activity.REST))}).run(1)
    assert kinds(world, EventKind.PRODUCTION) == []
    assert {r.health for r in world.residents} == {90}  # +5 recovery, +5 rest
    assert world.stats[-1].resting == 20


def test_config_rejects_nonsense() -> None:
    with pytest.raises(ValueError):
        SimulationConfig(num_residents=0)
    with pytest.raises(ValueError):
        SimulationConfig(initial_prices={"food": 0, "wood": 1, "stone": 1})
    with pytest.raises(ValueError):
        SimulationConfig(daily_needs={"food": 1})
    with pytest.raises(ValueError):
        replace(SimulationConfig(), skill_min=50, skill_max=40)
