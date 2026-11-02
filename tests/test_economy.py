"""Production, consumption and wealth statistics."""

from __future__ import annotations

import random

import pytest

from genesis.economy import consume_needs, daily_weather, gini, production_output, summarize_wealth
from genesis.models import Occupation, Resident, Resource, SimulationConfig

FOOD, WOOD, STONE = Resource.FOOD, Resource.WOOD, Resource.STONE


def farmer(skill: int = 100, health: int = 100, food: int = 5, wood: int = 5, stone: int = 5) -> Resident:
    return Resident(
        id=1,
        name="test",
        occupation=Occupation.FARMER,
        skills={Occupation.FARMER: skill, Occupation.WOODCUTTER: 100, Occupation.MINER: 100},
        cash=0,
        inventory={FOOD: food, WOOD: wood, STONE: stone},
        health=health,
    )


def test_production_at_full_health_and_skill_is_exactly_base_output() -> None:
    config = SimulationConfig()
    outputs = {production_output(farmer(), config, 100, random.Random(seed)) for seed in range(50)}
    assert outputs == {config.base_output[Occupation.FARMER]}


def test_production_averages_its_expectation() -> None:
    config = SimulationConfig()
    rng = random.Random(1)
    worker = farmer(skill=113, health=60)  # 5 x 1.13 x 0.90 x 1.04 = 5.2884 units
    draws = [production_output(worker, config, 104, rng) for _ in range(20_000)]
    assert set(draws) == {5, 6}
    assert sum(draws) / len(draws) == pytest.approx(5.288, abs=0.02)


def test_poor_health_reduces_output_to_three_quarters() -> None:
    config = SimulationConfig()
    assert production_output(farmer(health=0), config, 100, random.Random(0)) in (3, 4)  # 3.75 expected


def test_weather_stays_in_configured_range_and_is_reproducible() -> None:
    config = SimulationConfig(weather_min_pct=80, weather_max_pct=120)
    draws = [daily_weather(config, random.Random(seed)) for seed in range(200)]
    assert all(80 <= pct <= 120 for weather in draws for pct in weather.values())
    assert daily_weather(config, random.Random(5)) == daily_weather(config, random.Random(5))


def test_consumption_with_all_needs_met_recovers_health() -> None:
    config = SimulationConfig()
    worker = farmer(health=90)
    outcome = consume_needs(worker, config, rested=False)
    assert outcome.consumed == {FOOD: 1, WOOD: 1, STONE: 1}
    assert outcome.unmet == {FOOD: 0, WOOD: 0, STONE: 0}
    assert worker.inventory == {FOOD: 4, WOOD: 4, STONE: 4}
    assert (outcome.health_before, outcome.health_after) == (90, 95)


def test_unmet_needs_cost_health_and_never_go_negative() -> None:
    config = SimulationConfig()
    worker = farmer(health=50, food=0, wood=0, stone=3)
    outcome = consume_needs(worker, config, rested=False)
    assert outcome.unmet == {FOOD: 1, WOOD: 1, STONE: 0}
    assert worker.inventory == {FOOD: 0, WOOD: 0, STONE: 2}
    assert worker.health == 50 - 20 - 5


def test_rest_adds_recovery_and_health_is_capped() -> None:
    config = SimulationConfig()
    worker = farmer(health=97)
    consume_needs(worker, config, rested=True)
    assert worker.health == 100
    starving = farmer(health=10, food=0, wood=0, stone=0)
    consume_needs(starving, config, rested=True)
    assert starving.health == 0


def test_gini_reference_values() -> None:
    assert gini([]) == 0.0
    assert gini([0, 0]) == 0.0
    assert gini([5, 5, 5, 5]) == pytest.approx(0.0)
    assert gini([0, 0, 0, 100]) == pytest.approx(0.75)  # (n - 1) / n
    assert gini([1, 2, 3, 4]) == pytest.approx(0.25)


def test_wealth_summary() -> None:
    summary = summarize_wealth([100, 200, 300, 400, 1000])
    assert (summary.count, summary.total, summary.minimum, summary.maximum) == (5, 2000, 100, 1000)
    assert summary.mean == 400.0 and summary.median == 300.0
    assert summary.top_10_share == 0.5  # the richest one of five holds half
    assert summary.bottom_50_share == 0.15  # the poorest two hold 300 of 2000
    assert summarize_wealth([]).count == 0
