"""Plain data types shared by every GENESIS module.

Units
-----
Every quantity is an integer. Resources are counted in whole units and money in
integer *cents* (100 cents = 1 credit). Integer accounting is what makes the
conservation invariants exact: totals are compared with ``==``, never within a
floating-point tolerance. Floats appear only in derived statistics such as the
Gini coefficient.
"""

from __future__ import annotations

import enum
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, fields
from types import MappingProxyType
from typing import Any

MAX_HEALTH = 100
DEFAULT_POLICY = "rule_based"


class Resource(enum.StrEnum):
    FOOD = "food"
    WOOD = "wood"
    STONE = "stone"


class Occupation(enum.StrEnum):
    FARMER = "farmer"
    WOODCUTTER = "woodcutter"
    MINER = "miner"


#: Canonical iteration orders. Code that loops over resources or occupations uses
#: these tuples, so every run visits them in the same order.
RESOURCES: tuple[Resource, ...] = tuple(Resource)
OCCUPATIONS: tuple[Occupation, ...] = tuple(Occupation)

#: The resource each occupation produces.
PRODUCT: Mapping[Occupation, Resource] = MappingProxyType(
    {
        Occupation.FARMER: Resource.FOOD,
        Occupation.WOODCUTTER: Resource.WOOD,
        Occupation.MINER: Resource.STONE,
    }
)


class Side(enum.StrEnum):
    BUY = "buy"
    SELL = "sell"


class Activity(enum.StrEnum):
    WORK = "work"
    REST = "rest"


class EventKind(enum.StrEnum):
    WORLD_CREATED = "world_created"
    RESIDENT_CREATED = "resident_created"
    AGENT_ERROR = "agent_error"
    ACTION_REJECTED = "action_rejected"
    OCCUPATION_CHANGED = "occupation_changed"
    PRODUCTION = "production"
    ORDER_REJECTED = "order_rejected"
    TRADE = "trade"
    MARKET_CLEARED = "market_cleared"
    TAX = "tax"
    CONSUMPTION = "consumption"
    RESIDENT_DIED = "resident_died"


class GenesisError(Exception):
    """Base class for errors raised by GENESIS."""


class InvariantViolation(GenesisError):
    """The world state broke an accounting or consistency invariant."""


class SaveFormatError(GenesisError):
    """A save file is not a GENESIS world, is corrupt, or has an unsupported version."""


# --- small helpers -----------------------------------------------------------


def resource_map(raw: Mapping[Any, Any]) -> dict[Resource, Any]:
    """Return ``raw`` keyed by :class:`Resource`, in canonical order.

    Keys may be enum members or their string values; unknown keys raise
    ``ValueError``. Missing resources are left out (validation reports them).
    """
    converted = {Resource(key): value for key, value in raw.items()}
    return {resource: converted[resource] for resource in RESOURCES if resource in converted}


def occupation_map(raw: Mapping[Any, Any]) -> dict[Occupation, Any]:
    """Return ``raw`` keyed by :class:`Occupation`, in canonical order."""
    converted = {Occupation(key): value for key, value in raw.items()}
    return {occ: converted[occ] for occ in OCCUPATIONS if occ in converted}


def plain_map(mapping: Mapping[Any, Any]) -> dict[str, Any]:
    """Return a copy of ``mapping`` with plain-string keys, ready for JSON."""
    return {str(key): value for key, value in mapping.items()}


def is_int(value: object) -> bool:
    """True for real integers; ``bool`` is deliberately excluded."""
    return isinstance(value, int) and not isinstance(value, bool)


def _check_int(name: str, value: object, minimum: int | None = None, maximum: int | None = None) -> None:
    if not is_int(value):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    assert isinstance(value, int)
    if minimum is not None and value < minimum:
        raise ValueError(f"{name} must be >= {minimum}, got {value}")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}, got {value}")


def _check_map(name: str, mapping: Mapping[Any, Any], keys: tuple[Any, ...], minimum: int) -> None:
    if set(mapping) != set(keys):
        raise ValueError(f"{name} must have exactly the keys {[str(k) for k in keys]}")
    for key in keys:
        _check_int(f"{name}[{key}]", mapping[key], minimum)


def _resources(food: int, wood: int, stone: int) -> Callable[[], dict[Resource, int]]:
    return lambda: {Resource.FOOD: food, Resource.WOOD: wood, Resource.STONE: stone}


# --- configuration -----------------------------------------------------------

_RESOURCE_MAP_FIELDS = ("initial_inventory", "initial_prices", "daily_needs", "unmet_need_penalty")
_OCCUPATION_MAP_FIELDS = ("base_output",)


@dataclass(frozen=True, slots=True)
class SimulationConfig:
    """Tunable parameters of a world. Money is in cents, rates in percent or bps.

    The defaults describe a small, deliberately simple economy; see
    ``docs/ECONOMY.md`` for what each rule means and what it leaves out.
    """

    num_residents: int = 20
    #: Starting cash per resident, in cents (10_000 = 100.00 credits).
    initial_cash: int = 10_000
    initial_inventory: dict[Resource, int] = field(default_factory=_resources(5, 5, 5))
    #: Opening reference prices, in cents per unit.
    initial_prices: dict[Resource, int] = field(default_factory=_resources(300, 400, 500))
    #: Units each living resident consumes per day.
    daily_needs: dict[Resource, int] = field(default_factory=_resources(1, 1, 1))
    #: Health lost per missing unit of a daily need.
    unmet_need_penalty: dict[Resource, int] = field(default_factory=_resources(20, 5, 3))
    #: Units produced per working day at 100 % skill, health and weather.
    base_output: dict[Occupation, int] = field(
        default_factory=lambda: {Occupation.FARMER: 5, Occupation.WOODCUTTER: 4, Occupation.MINER: 3}
    )
    #: Range of per-occupation skill drawn at creation, in percent of base output.
    skill_min: int = 75
    skill_max: int = 125
    #: Range of the daily, per-resource productivity shock, in percent.
    weather_min_pct: int = 90
    weather_max_pct: int = 110
    #: Health regained on a day with every need met.
    health_recovery: int = 5
    #: Extra health regained on a day spent resting.
    rest_recovery: int = 5
    min_price: int = 1
    max_price: int = 1_000_000
    max_orders_per_day: int = 10
    max_order_quantity: int = 1_000
    #: Reference-price move (basis points) when an auction has only one side.
    no_trade_price_step_bps: int = 500
    #: Minimum days between two occupation changes of one resident.
    occupation_cooldown_days: int = 7

    def __post_init__(self) -> None:
        # Copy and canonicalise mapping fields so callers may pass string keys and
        # later mutation of the caller's dicts cannot leak into the config.
        for name in _RESOURCE_MAP_FIELDS:
            object.__setattr__(self, name, resource_map(getattr(self, name)))
        for name in _OCCUPATION_MAP_FIELDS:
            object.__setattr__(self, name, occupation_map(getattr(self, name)))
        self.validate()

    def validate(self) -> None:
        """Raise ``ValueError`` if the configuration is inconsistent."""
        _check_int("num_residents", self.num_residents, 1, 100_000)
        _check_int("initial_cash", self.initial_cash, 0)
        if self.initial_cash * self.num_residents >= 2**62:
            raise ValueError("total money supply is too large to store")
        _check_int("min_price", self.min_price, 1)
        _check_int("max_price", self.max_price, self.min_price, 2**40)
        _check_map("initial_inventory", self.initial_inventory, RESOURCES, 0)
        _check_map("initial_prices", self.initial_prices, RESOURCES, self.min_price)
        for resource in RESOURCES:
            _check_int(f"initial_prices[{resource}]", self.initial_prices[resource], maximum=self.max_price)
        _check_map("daily_needs", self.daily_needs, RESOURCES, 0)
        _check_map("unmet_need_penalty", self.unmet_need_penalty, RESOURCES, 0)
        _check_map("base_output", self.base_output, OCCUPATIONS, 0)
        _check_int("skill_min", self.skill_min, 1)
        _check_int("skill_max", self.skill_max, self.skill_min)
        _check_int("weather_min_pct", self.weather_min_pct, 0)
        _check_int("weather_max_pct", self.weather_max_pct, self.weather_min_pct)
        _check_int("health_recovery", self.health_recovery, 0, MAX_HEALTH)
        _check_int("rest_recovery", self.rest_recovery, 0, MAX_HEALTH)
        _check_int("max_orders_per_day", self.max_orders_per_day, 0)
        _check_int("max_order_quantity", self.max_order_quantity, 1)
        _check_int("no_trade_price_step_bps", self.no_trade_price_step_bps, 0, 9_999)
        _check_int("occupation_cooldown_days", self.occupation_cooldown_days, 0)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            result[f.name] = plain_map(value) if isinstance(value, Mapping) else value
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> SimulationConfig:
        """Build a config from :meth:`to_dict` output. Missing fields take defaults."""
        known = {f.name for f in fields(cls)}
        unknown = sorted(set(data) - known)
        if unknown:
            raise ValueError(f"unknown configuration fields: {', '.join(unknown)}")
        return cls(**dict(data))


# --- world state records -------------------------------------------------------


@dataclass(slots=True)
class Resident:
    """One autonomous resident. Mutated only by the simulation engine."""

    id: int
    name: str
    occupation: Occupation
    #: Productivity in each occupation, in percent of the base output.
    skills: dict[Occupation, int]
    cash: int
    inventory: dict[Resource, int]
    health: int = MAX_HEALTH
    alive: bool = True
    #: Key of the agent policy that decides for this resident.
    policy: str = DEFAULT_POLICY
    last_occupation_change: int | None = None
    died_on: int | None = None

    @property
    def product(self) -> Resource:
        return PRODUCT[self.occupation]

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "occupation": str(self.occupation),
            "skills": plain_map(self.skills),
            "cash": self.cash,
            "inventory": plain_map(self.inventory),
            "health": self.health,
            "alive": self.alive,
            "policy": self.policy,
            "last_occupation_change": self.last_occupation_change,
            "died_on": self.died_on,
        }


@dataclass(slots=True)
class MarketQuote:
    """Public market information for one resource, as of the latest auction."""

    #: Reference price in cents: the latest clearing price, or a nudge from it
    #: when the latest auction did not trade.
    price: int
    #: Units bid, units offered and units traded in the latest auction.
    demand: int = 0
    supply: int = 0
    volume: int = 0

    def to_dict(self) -> dict[str, int]:
        return {"price": self.price, "demand": self.demand, "supply": self.supply, "volume": self.volume}


@dataclass(slots=True)
class Ledger:
    """Cumulative totals that the conservation invariants are checked against."""

    #: Total cash in existence. No mechanism creates or destroys money in v0.1.
    money_supply: int
    #: Units of each resource handed out when the world was created.
    initial: dict[Resource, int]
    produced: dict[Resource, int] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0))
    consumed: dict[Resource, int] = field(default_factory=lambda: dict.fromkeys(RESOURCES, 0))

    def expected_holdings(self, resource: Resource) -> int:
        """Units that must exist: initial + produced - consumed."""
        return self.initial[resource] + self.produced[resource] - self.consumed[resource]

    def to_dict(self) -> dict[str, Any]:
        return {
            "money_supply": self.money_supply,
            "initial": plain_map(self.initial),
            "produced": plain_map(self.produced),
            "consumed": plain_map(self.consumed),
        }


@dataclass(frozen=True, slots=True)
class Event:
    """One entry of the append-only event log. ``data`` holds JSON-native values only."""

    seq: int
    day: int
    kind: EventKind
    resident_id: int | None = None
    #: The other party of a two-sided event, e.g. the seller of a trade.
    counterparty_id: int | None = None
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "seq": self.seq,
            "day": self.day,
            "kind": str(self.kind),
            "resident_id": self.resident_id,
            "counterparty_id": self.counterparty_id,
            "data": self.data,
        }


_STATS_RESOURCE_FIELDS = (
    "prices",
    "production",
    "consumption",
    "unmet_needs",
    "demand",
    "supply",
    "trade_volume",
    "trade_value",
    "holdings",
)


@dataclass(frozen=True, slots=True)
class DailyStats:
    """Aggregate metrics recorded at the end of each simulated day."""

    day: int
    population: int
    deaths: int
    working: int
    resting: int
    occupations: dict[Occupation, int]
    prices: dict[Resource, int]
    production: dict[Resource, int]
    consumption: dict[Resource, int]
    unmet_needs: dict[Resource, int]
    demand: dict[Resource, int]
    supply: dict[Resource, int]
    trade_volume: dict[Resource, int]
    trade_value: dict[Resource, int]
    trade_count: int
    rejected_orders: int
    #: Units held by all residents, living and dead.
    holdings: dict[Resource, int]
    money_supply: int
    mean_health: float
    #: Cash plus inventory at reference prices, summed over living residents.
    total_wealth: int
    gini: float

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            result[f.name] = plain_map(value) if isinstance(value, Mapping) else value
        return result

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> DailyStats:
        values = dict(data)
        values["occupations"] = occupation_map(values["occupations"])
        for name in _STATS_RESOURCE_FIELDS:
            values[name] = resource_map(values[name])
        return cls(**values)


# --- the agent interface -------------------------------------------------------


@dataclass(frozen=True, slots=True)
class OrderRequest:
    """A limit order proposed by an agent. The engine decides whether it is valid.

    A buy order is willing to pay *up to* ``limit_price`` cents per unit; a sell
    order accepts *no less than* ``limit_price``. Every trade executes at the
    auction's single clearing price.
    """

    side: Side
    resource: Resource
    quantity: int
    limit_price: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "side": str(self.side),
            "resource": str(self.resource),
            "quantity": self.quantity,
            "limit_price": self.limit_price,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> OrderRequest:
        """Parse an order from plain data. Raises ``ValueError`` on malformed input."""
        if not isinstance(data, Mapping):
            raise ValueError("an order must be an object")
        expected = {"side", "resource", "quantity", "limit_price"}
        if set(data) != expected:
            raise ValueError(f"an order must have exactly the fields {sorted(expected)}")
        for name in ("quantity", "limit_price"):
            if not is_int(data[name]):
                raise ValueError(f"order {name} must be an integer, got {data[name]!r}")
        return cls(Side(data["side"]), Resource(data["resource"]), data["quantity"], data["limit_price"])


@dataclass(frozen=True, slots=True)
class Decision:
    """Everything one resident proposes for one day.

    The engine is authoritative: each invalid part of a decision is rejected
    and logged, and the valid parts still apply.
    """

    activity: Activity = Activity.WORK
    orders: tuple[OrderRequest, ...] = ()
    #: Occupation to switch to before today's work, or ``None`` to stay.
    new_occupation: Occupation | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "activity": str(self.activity),
            "orders": [order.to_dict() for order in self.orders],
            "new_occupation": None if self.new_occupation is None else str(self.new_occupation),
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Decision:
        """Parse a decision from plain data, such as JSON returned by a language model.

        Raises ``ValueError`` on malformed input. Parsing checks shape and types
        only; whether the actions are *allowed* is decided later by the engine.
        """
        if not isinstance(data, Mapping):
            raise ValueError("a decision must be an object")
        unknown = sorted(set(data) - {"activity", "orders", "new_occupation"})
        if unknown:
            raise ValueError(f"unknown decision fields: {', '.join(unknown)}")
        raw_orders = data.get("orders", [])
        if not isinstance(raw_orders, list | tuple):
            raise ValueError("decision orders must be a list")
        occupation = data.get("new_occupation")
        return cls(
            activity=Activity(data.get("activity", Activity.WORK)),
            orders=tuple(OrderRequest.from_dict(order) for order in raw_orders),
            new_occupation=None if occupation is None else Occupation(occupation),
        )


@dataclass(frozen=True, slots=True)
class Rules:
    """World rules an agent can rely on. Read-only; shared by all agents."""

    daily_needs: Mapping[Resource, int]
    unmet_need_penalty: Mapping[Resource, int]
    health_recovery: int
    rest_recovery: int
    base_output: Mapping[Occupation, int]
    products: Mapping[Occupation, Resource]
    min_price: int
    max_price: int
    max_orders_per_day: int
    max_order_quantity: int
    occupation_cooldown_days: int

    @classmethod
    def from_config(cls, config: SimulationConfig) -> Rules:
        return cls(
            daily_needs=MappingProxyType(dict(config.daily_needs)),
            unmet_need_penalty=MappingProxyType(dict(config.unmet_need_penalty)),
            health_recovery=config.health_recovery,
            rest_recovery=config.rest_recovery,
            base_output=MappingProxyType(dict(config.base_output)),
            products=PRODUCT,
            min_price=config.min_price,
            max_price=config.max_price,
            max_orders_per_day=config.max_orders_per_day,
            max_order_quantity=config.max_order_quantity,
            occupation_cooldown_days=config.occupation_cooldown_days,
        )

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if isinstance(value, Mapping):
                value = {
                    str(key): str(item) if isinstance(item, enum.Enum) else item
                    for key, item in value.items()
                }
            result[f.name] = value
        return result


@dataclass(frozen=True, slots=True)
class Observation:
    """What one resident knows when it decides. Built fresh for every decision.

    Every mapping is a private copy, so an agent cannot change the world by
    mutating its observation.
    """

    day: int
    resident_id: int
    name: str
    occupation: Occupation
    can_change_occupation: bool
    health: int
    cash: int
    inventory: dict[Resource, int]
    skills: dict[Occupation, int]
    market: dict[Resource, MarketQuote]
    #: Living residents at the start of the day.
    population: int
    #: Living residents per occupation at the start of the day (public census).
    census: dict[Occupation, int]
    #: Total cash in existence (constant in v0.1: nothing creates or destroys money).
    money_supply: int
    rules: Rules

    def to_dict(self) -> dict[str, Any]:
        """Return a JSON-ready view, e.g. for rendering into a language-model prompt."""
        return {
            "day": self.day,
            "resident_id": self.resident_id,
            "name": self.name,
            "occupation": str(self.occupation),
            "can_change_occupation": self.can_change_occupation,
            "health": self.health,
            "cash": self.cash,
            "inventory": plain_map(self.inventory),
            "skills": plain_map(self.skills),
            "market": {str(resource): quote.to_dict() for resource, quote in self.market.items()},
            "population": self.population,
            "census": plain_map(self.census),
            "money_supply": self.money_supply,
            "rules": self.rules.to_dict(),
        }
