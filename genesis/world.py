"""Authoritative world state and world creation."""

from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass, field
from typing import Any

from genesis.models import (
    DEFAULT_POLICY,
    OCCUPATIONS,
    RESOURCES,
    DailyStats,
    Event,
    EventKind,
    Ledger,
    MarketQuote,
    Resident,
    Resource,
    SimulationConfig,
    is_int,
    plain_map,
)

NAME_POOL: tuple[str, ...] = (
    "Ada", "Bram", "Chiara", "Dmitri", "Eshe", "Farid", "Greta", "Hiro", "Ines", "Jonas",
    "Kalani", "Lior", "Mei", "Nadia", "Omar", "Priya", "Quentin", "Rosa", "Sven", "Tamar",
    "Ulla", "Vikram", "Wanjiru", "Xavier", "Yara", "Zeno", "Amara", "Bilal", "Celine", "Darius",
    "Elena", "Femi", "Gael", "Hana", "Idris", "Juno", "Kofi", "Lena", "Mateo", "Noor",
)  # fmt: skip


def derive_rng(seed: int, day: int, stream: str) -> random.Random:
    """Return a reproducible random generator for one purpose on one day.

    Each (seed, day, stream) triple gets its own generator instead of all phases
    sharing one. A random draw added to one phase therefore never shifts the
    numbers another phase sees, and a world restored from a save continues with
    exactly the numbers it would have used had it never been saved, without
    storing generator state. String seeds are hashed with SHA-512 by
    :mod:`random`, so they do not depend on ``PYTHONHASHSEED``.
    """
    return random.Random(f"genesis:{seed}:{day}:{stream}")


@dataclass(slots=True)
class World:
    """Everything that defines a simulation run.

    Only the simulation engine mutates a world. Agents never receive a
    reference to it; they get an :class:`~genesis.models.Observation` instead.
    ``day`` is the last day simulated (0 for a freshly created world).
    """

    seed: int
    config: SimulationConfig
    residents: list[Resident]
    market: dict[Resource, MarketQuote]
    ledger: Ledger
    day: int = 0
    events: list[Event] = field(default_factory=list)
    stats: list[DailyStats] = field(default_factory=list)

    def rng(self, day: int, stream: str) -> random.Random:
        return derive_rng(self.seed, day, stream)

    def resident(self, resident_id: int) -> Resident:
        for resident in self.residents:
            if resident.id == resident_id:
                return resident
        raise KeyError(f"no resident with id {resident_id}")

    def living(self) -> list[Resident]:
        return [resident for resident in self.residents if resident.alive]

    def record(
        self,
        kind: EventKind,
        *,
        resident_id: int | None = None,
        counterparty_id: int | None = None,
        **data: Any,
    ) -> Event:
        """Append an event for the current day. ``data`` must be JSON-native."""
        event = Event(
            seq=len(self.events) + 1,
            day=self.day,
            kind=kind,
            resident_id=resident_id,
            counterparty_id=counterparty_id,
            data=data,
        )
        self.events.append(event)
        return event

    def total_cash(self) -> int:
        return sum(resident.cash for resident in self.residents)

    def holdings(self, *, living_only: bool = False) -> dict[Resource, int]:
        """Units of each resource held by residents (estates of the dead included by default)."""
        totals = dict.fromkeys(RESOURCES, 0)
        for resident in self.residents:
            if living_only and not resident.alive:
                continue
            for resource in RESOURCES:
                totals[resource] += resident.inventory[resource]
        return totals

    def prices(self) -> dict[Resource, int]:
        return {resource: self.market[resource].price for resource in RESOURCES}

    def wealth(self, resident: Resident) -> int:
        """Cash plus inventory valued at current reference prices, in cents."""
        return resident.cash + sum(
            resident.inventory[resource] * self.market[resource].price for resource in RESOURCES
        )

    def to_dict(self) -> dict[str, Any]:
        """Canonical JSON-ready form of the whole world, events included."""
        return {
            "seed": self.seed,
            "day": self.day,
            "config": self.config.to_dict(),
            "residents": [resident.to_dict() for resident in self.residents],
            "market": {str(resource): self.market[resource].to_dict() for resource in RESOURCES},
            "ledger": self.ledger.to_dict(),
            "events": [event.to_dict() for event in self.events],
            "stats": [stats.to_dict() for stats in self.stats],
        }

    def state_digest(self) -> str:
        """SHA-256 of :meth:`to_dict` as canonical JSON.

        Two runs are identical exactly when their digests match, which makes the
        digest a cheap way to compare runs across machines and save/load cycles.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def create_world(
    config: SimulationConfig | None = None,
    *,
    seed: int = 42,
    policy: str = DEFAULT_POLICY,
) -> World:
    """Create a world at day 0. The same config and seed always give the same world.

    Every resident gets a skill in each occupation drawn from the configured
    range and starts in the occupation they are most skilled at, with the
    configured cash and inventory.
    """
    config = config if config is not None else SimulationConfig()
    if not is_int(seed):
        raise ValueError(f"seed must be an integer, got {seed!r}")
    rng = derive_rng(seed, 0, "genesis")
    names = _resident_names(rng, config.num_residents)
    residents: list[Resident] = []
    for index in range(config.num_residents):
        skills = {occ: rng.randint(config.skill_min, config.skill_max) for occ in OCCUPATIONS}
        best = max(OCCUPATIONS, key=lambda occ: skills[occ])
        residents.append(
            Resident(
                id=index + 1,
                name=names[index],
                occupation=best,
                skills=skills,
                cash=config.initial_cash,
                inventory=dict(config.initial_inventory),
                policy=policy,
            )
        )

    world = World(
        seed=seed,
        config=config,
        residents=residents,
        market={resource: MarketQuote(price=config.initial_prices[resource]) for resource in RESOURCES},
        ledger=Ledger(
            money_supply=config.initial_cash * config.num_residents,
            initial={
                resource: config.initial_inventory[resource] * config.num_residents for resource in RESOURCES
            },
        ),
    )
    world.record(
        EventKind.WORLD_CREATED,
        seed=seed,
        residents=config.num_residents,
        money_supply=world.ledger.money_supply,
        prices=plain_map(world.prices()),
    )
    for resident in residents:
        # The genesis allocation: replaying the event log starts from these records.
        world.record(
            EventKind.RESIDENT_CREATED,
            resident_id=resident.id,
            name=resident.name,
            occupation=str(resident.occupation),
            skills=plain_map(resident.skills),
            cash=resident.cash,
            inventory=plain_map(resident.inventory),
            policy=resident.policy,
        )
    return world


def _resident_names(rng: random.Random, count: int) -> list[str]:
    pool = rng.sample(NAME_POOL, len(NAME_POOL))
    names: list[str] = []
    for index in range(count):
        generation = index // len(pool)
        base = pool[index % len(pool)]
        names.append(base if generation == 0 else f"{base} {generation + 1}")
    return names
