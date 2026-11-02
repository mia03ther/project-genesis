"""Shared fixtures and helpers for the GENESIS test suite."""

from __future__ import annotations

import pytest

from genesis.economy import Order
from genesis.models import Resource, Side
from genesis.simulation import Simulation
from genesis.world import World, create_world


def make_order(
    seq: int,
    resident_id: int,
    side: Side,
    quantity: int,
    price: int,
    resource: Resource = Resource.FOOD,
) -> Order:
    return Order(
        seq=seq, resident_id=resident_id, side=side, resource=resource, quantity=quantity, limit_price=price
    )


def run_world(days: int, seed: int = 42, **kwargs: object) -> World:
    world = create_world(seed=seed)
    Simulation(world, **kwargs).run(days)  # type: ignore[arg-type]
    return world


@pytest.fixture(scope="session")
def world_100() -> World:
    """A world after 100 days with the default configuration. Do not mutate."""
    return run_world(100)
