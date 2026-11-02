"""Economic rules: production, consumption, order validation and market clearing.

These functions encode *how* the economy works; :mod:`genesis.simulation`
decides *when* they run and records the results. Most are pure functions of
their arguments, so they can be tested without building a world.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import asdict, dataclass
from typing import Any

from genesis.models import (
    MAX_HEALTH,
    RESOURCES,
    InvariantViolation,
    OrderRequest,
    Resident,
    Resource,
    Side,
    SimulationConfig,
    is_int,
)

#: Basis points in 100 %.
BPS = 10_000


# --- production ----------------------------------------------------------------


def daily_weather(config: SimulationConfig, rng: random.Random) -> dict[Resource, int]:
    """Draw today's productivity modifier, in percent, for each resource."""
    return {resource: rng.randint(config.weather_min_pct, config.weather_max_pct) for resource in RESOURCES}


def production_output(
    resident: Resident, config: SimulationConfig, weather_pct: int, rng: random.Random
) -> int:
    """Units a working resident produces today.

    The expectation is ``base_output x skill% x vitality% x weather%``, where
    vitality falls linearly from 100 % at full health to 75 % at zero health.
    The fractional part is resolved by stochastic rounding, so the long-run
    average equals the expectation while every single output is an integer.
    Exactly one random number is drawn per call.
    """
    occupation = resident.occupation
    vitality_pct = 75 + resident.health // 4
    expected_milli = (
        config.base_output[occupation] * resident.skills[occupation] * vitality_pct * weather_pct
    ) // 1_000
    whole, fraction = divmod(expected_milli, 1_000)
    return whole + (1 if rng.randrange(1_000) < fraction else 0)


# --- consumption ---------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ConsumptionOutcome:
    consumed: dict[Resource, int]
    unmet: dict[Resource, int]
    health_before: int
    health_after: int


def consume_needs(resident: Resident, config: SimulationConfig, *, rested: bool) -> ConsumptionOutcome:
    """Consume one day of needs from the resident's own inventory and update health.

    Each missing unit costs ``unmet_need_penalty`` health. A day with every
    need met restores ``health_recovery``; a rest day adds ``rest_recovery``.
    Health stays within ``0..MAX_HEALTH``.
    """
    consumed: dict[Resource, int] = {}
    unmet: dict[Resource, int] = {}
    change = 0
    for resource in RESOURCES:
        need = config.daily_needs[resource]
        used = min(need, resident.inventory[resource])
        resident.inventory[resource] -= used
        consumed[resource] = used
        unmet[resource] = need - used
        change -= unmet[resource] * config.unmet_need_penalty[resource]
    if not any(unmet.values()):
        change += config.health_recovery
    if rested:
        change += config.rest_recovery
    before = resident.health
    resident.health = max(0, min(MAX_HEALTH, before + change))
    return ConsumptionOutcome(consumed, unmet, before, resident.health)


# --- order validation ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class Order:
    """An order that passed validation. Its cash or goods are reserved for the day."""

    #: Global arrival sequence; lower means earlier (time priority).
    seq: int
    resident_id: int
    side: Side
    resource: Resource
    quantity: int
    limit_price: int


@dataclass(frozen=True, slots=True)
class OrderRejection:
    resident_id: int
    reason: str
    #: JSON-safe description of what was submitted.
    order: dict[str, Any]


def validate_orders(
    submissions: Iterable[tuple[Resident, object]],
    config: SimulationConfig,
) -> tuple[list[Order], list[OrderRejection]]:
    """Validate proposed orders and reserve what each accepted order needs.

    ``submissions`` pairs each resident with the orders it proposed and is
    processed in the given order, which also becomes the auction's time
    priority. A buy order reserves ``quantity x limit_price`` cents and a sell
    order reserves ``quantity`` units, so every accepted order can settle in
    full at once and no balance can go negative, whatever the clearing prices.
    Proceeds of today's sales can therefore only be spent tomorrow.

    Rejection reasons: ``malformed_order``, ``invalid_quantity``,
    ``invalid_price``, ``self_cross`` (buying and selling one resource on the
    same day), ``insufficient_funds``, ``insufficient_inventory`` and
    ``too_many_orders`` (reported once for all orders past the daily limit).
    """
    accepted: list[Order] = []
    rejected: list[OrderRejection] = []
    for resident, requests in submissions:
        if not isinstance(requests, list | tuple):
            rejected.append(OrderRejection(resident.id, "malformed_order", {"orders": _jsonable(requests)}))
            continue
        cash_reserved = 0
        goods_reserved = dict.fromkeys(RESOURCES, 0)
        sides: dict[Resource, Side] = {}
        for request in requests[: config.max_orders_per_day]:
            parsed = _parse(request, config)
            if isinstance(parsed, str):
                reason = parsed
            else:
                side, resource, quantity, price = parsed
                if sides.get(resource, side) is not side:
                    reason = "self_cross"
                elif side is Side.BUY and cash_reserved + quantity * price > resident.cash:
                    reason = "insufficient_funds"
                elif side is Side.SELL and goods_reserved[resource] + quantity > resident.inventory[resource]:
                    reason = "insufficient_inventory"
                else:
                    if side is Side.BUY:
                        cash_reserved += quantity * price
                    else:
                        goods_reserved[resource] += quantity
                    sides[resource] = side
                    accepted.append(Order(len(accepted) + 1, resident.id, side, resource, quantity, price))
                    continue
            rejected.append(OrderRejection(resident.id, reason, _describe(request)))
        excess = len(requests) - config.max_orders_per_day
        if excess > 0:
            rejected.append(OrderRejection(resident.id, "too_many_orders", {"excess_orders": excess}))
    return accepted, rejected


def _parse(request: object, config: SimulationConfig) -> tuple[Side, Resource, int, int] | str:
    """Return an order's fields, or why the order is invalid on its own terms.

    Agents are untrusted, so nothing about ``request`` is assumed, not even
    that its fields have the annotated types.
    """
    if not isinstance(request, OrderRequest):
        return "malformed_order"
    try:
        side, resource = Side(request.side), Resource(request.resource)
    except (ValueError, TypeError):
        return "malformed_order"
    quantity, price = request.quantity, request.limit_price
    if not is_int(quantity) or not 1 <= quantity <= config.max_order_quantity:
        return "invalid_quantity"
    if not is_int(price) or not config.min_price <= price <= config.max_price:
        return "invalid_price"
    return side, resource, quantity, price


def _jsonable(value: object) -> object:
    if value is None or is_int(value) or isinstance(value, bool):
        return value
    if isinstance(value, str):
        return str(value)[:40]
    return repr(value)[:60]


def _describe(request: object) -> dict[str, Any]:
    if isinstance(request, OrderRequest):
        return {
            "side": _jsonable(request.side),
            "resource": _jsonable(request.resource),
            "quantity": _jsonable(request.quantity),
            "limit_price": _jsonable(request.limit_price),
        }
    return {"value": _jsonable(request)}


# --- the daily call auction ----------------------------------------------------


@dataclass(frozen=True, slots=True)
class Trade:
    resource: Resource
    buyer_id: int
    seller_id: int
    quantity: int
    #: The auction's uniform clearing price, in cents per unit.
    price: int

    @property
    def value(self) -> int:
        return self.quantity * self.price


@dataclass(frozen=True, slots=True)
class AuctionResult:
    resource: Resource
    #: ``None`` when nothing traded.
    clearing_price: int | None
    #: Total units bid and offered, whether or not they traded.
    demand: int
    supply: int
    volume: int
    trades: tuple[Trade, ...]
    best_bid: int | None
    best_ask: int | None

    @property
    def value(self) -> int:
        return sum(trade.value for trade in self.trades)


def clear_auction(resource: Resource, orders: Sequence[Order], reference_price: int) -> AuctionResult:
    """Clear one resource's daily call auction at a single uniform price.

    All orders for the day are collected first, then matched at once. The
    clearing price follows the usual call-auction rules, in order:

    1. maximise the traded volume;
    2. minimise the leftover imbalance between demand and supply;
    3. if only buyers are left over, take the highest such price, if only
       sellers are left over, the lowest (market pressure);
    4. otherwise take the price closest to the reference price, then the lower.

    Buyers are served by highest limit and sellers by lowest limit. Orders at
    the marginal limit price share what is left pro rata to their size, with
    leftover single units going by arrival. Every trade executes at the
    clearing price, which never exceeds a matched buyer's limit nor falls below
    a matched seller's limit.
    """
    bids = [order for order in orders if order.resource == resource and order.side is Side.BUY]
    asks = [order for order in orders if order.resource == resource and order.side is Side.SELL]
    demand = sum(order.quantity for order in bids)
    supply = sum(order.quantity for order in asks)
    best_bid = max((order.limit_price for order in bids), default=None)
    best_ask = min((order.limit_price for order in asks), default=None)
    if best_bid is None or best_ask is None or best_bid < best_ask:
        return AuctionResult(resource, None, demand, supply, 0, (), best_bid, best_ask)

    price = _clearing_price(bids, asks, reference_price)
    buyers = sorted((o for o in bids if o.limit_price >= price), key=lambda o: (-o.limit_price, o.seq))
    sellers = sorted((o for o in asks if o.limit_price <= price), key=lambda o: (o.limit_price, o.seq))
    volume = min(sum(o.quantity for o in buyers), sum(o.quantity for o in sellers))
    trades = _match(resource, price, _allocate(buyers, volume), _allocate(sellers, volume))
    return AuctionResult(resource, price, demand, supply, volume, tuple(trades), best_bid, best_ask)


def _clearing_price(bids: Sequence[Order], asks: Sequence[Order], reference_price: int) -> int:
    candidates = sorted({o.limit_price for o in bids} | {o.limit_price for o in asks} | {reference_price})
    scored: list[tuple[int, int, int]] = []  # (price, volume, demand - supply)
    for price in candidates:
        demand = sum(o.quantity for o in bids if o.limit_price >= price)
        supply = sum(o.quantity for o in asks if o.limit_price <= price)
        if min(demand, supply) > 0:
            scored.append((price, min(demand, supply), demand - supply))
    best_volume = max(volume for _, volume, _ in scored)
    scored = [s for s in scored if s[1] == best_volume]
    least_imbalance = min(abs(imbalance) for _, _, imbalance in scored)
    scored = [s for s in scored if abs(s[2]) == least_imbalance]
    if all(imbalance > 0 for _, _, imbalance in scored):
        return max(price for price, _, _ in scored)
    if all(imbalance < 0 for _, _, imbalance in scored):
        return min(price for price, _, _ in scored)
    return min(scored, key=lambda s: (abs(s[0] - reference_price), s[0]))[0]


def _allocate(orders: Sequence[Order], volume: int) -> list[tuple[Order, int]]:
    """Fill ``volume`` units from ``orders``, which are sorted best price first.

    Price levels are filled in order. The first level that cannot be filled
    completely is rationed pro rata to order size; the units lost to rounding
    go one each to the earliest arrivals. Integer arithmetic keeps it exact.
    """
    fills: list[tuple[Order, int]] = []
    remaining = volume
    index = 0
    while remaining > 0 and index < len(orders):
        level = [order for order in orders[index:] if order.limit_price == orders[index].limit_price]
        index += len(level)
        level_quantity = sum(order.quantity for order in level)
        if level_quantity <= remaining:
            fills.extend((order, order.quantity) for order in level)
            remaining -= level_quantity
            continue
        shares = {order.seq: order.quantity * remaining // level_quantity for order in level}
        leftover = remaining - sum(shares.values())
        for order in sorted(level, key=lambda o: o.seq)[:leftover]:
            shares[order.seq] += 1
        fills.extend((order, shares[order.seq]) for order in level if shares[order.seq] > 0)
        remaining = 0
    return fills


def _match(
    resource: Resource,
    price: int,
    buys: Sequence[tuple[Order, int]],
    sells: Sequence[tuple[Order, int]],
) -> list[Trade]:
    """Pair filled buy and sell quantities into bilateral trades."""
    trades: list[Trade] = []
    b = s = 0
    buy_left = buys[0][1] if buys else 0
    sell_left = sells[0][1] if sells else 0
    while b < len(buys) and s < len(sells):
        quantity = min(buy_left, sell_left)
        trades.append(Trade(resource, buys[b][0].resident_id, sells[s][0].resident_id, quantity, price))
        buy_left -= quantity
        sell_left -= quantity
        if buy_left == 0:
            b += 1
            buy_left = buys[b][1] if b < len(buys) else 0
        if sell_left == 0:
            s += 1
            sell_left = sells[s][1] if s < len(sells) else 0
    return trades


def settle_trades(trades: Iterable[Trade], residents: Mapping[int, Resident]) -> None:
    """Move goods and money for executed trades.

    Escrow at validation time already guarantees that every check below
    passes. The checks stay as a last line of defence: a bug elsewhere must
    surface as an :class:`InvariantViolation`, never as created or destroyed assets.
    """
    for trade in trades:
        buyer = residents[trade.buyer_id]
        seller = residents[trade.seller_id]
        if buyer is seller:
            raise InvariantViolation(f"resident {buyer.id} traded with themself")
        if trade.quantity <= 0 or trade.price <= 0:
            raise InvariantViolation(f"invalid trade {trade}")
        if buyer.cash < trade.value:
            raise InvariantViolation(f"buyer {buyer.id} cannot pay {trade.value} cents")
        if seller.inventory[trade.resource] < trade.quantity:
            raise InvariantViolation(f"seller {seller.id} cannot deliver {trade.quantity} {trade.resource}")
        buyer.cash -= trade.value
        seller.cash += trade.value
        seller.inventory[trade.resource] -= trade.quantity
        buyer.inventory[trade.resource] += trade.quantity


def next_reference_price(previous: int, result: AuctionResult, config: SimulationConfig) -> int:
    """Tomorrow's reference price for a resource.

    After a trade it is the clearing price. Without a trade it moves by
    ``no_trade_price_step_bps``: up if there were only buyers, down if there
    were only sellers, and toward the middle of the spread if both sides were
    present but did not cross. It is always kept within the configured bounds.
    """
    step = config.no_trade_price_step_bps
    if result.clearing_price is not None:
        price = result.clearing_price
    elif result.demand > 0 and result.supply == 0:
        price = _raise(previous, step)
    elif result.supply > 0 and result.demand == 0:
        price = _lower(previous, step)
    elif result.best_bid is not None and result.best_ask is not None:
        midpoint = (result.best_bid + result.best_ask) // 2
        price = max(_lower(previous, step), min(_raise(previous, step), midpoint))
    else:
        price = previous
    return max(config.min_price, min(config.max_price, price))


def _raise(price: int, step_bps: int) -> int:
    if step_bps == 0:
        return price
    return max(price + 1, -(-price * (BPS + step_bps) // BPS))


def _lower(price: int, step_bps: int) -> int:
    if step_bps == 0:
        return price
    return min(price - 1, price * (BPS - step_bps) // BPS)


# --- wealth --------------------------------------------------------------------


def gini(values: Sequence[int]) -> float:
    """Gini coefficient of non-negative values: 0 is perfect equality,
    ``(n - 1) / n`` means one holder owns everything."""
    count = len(values)
    total = sum(values)
    if count == 0 or total == 0:
        return 0.0
    weighted = sum(rank * value for rank, value in enumerate(sorted(values), start=1))
    return (2 * weighted) / (count * total) - (count + 1) / count


@dataclass(frozen=True, slots=True)
class WealthSummary:
    """Distribution of wealth (in cents) across a group of residents."""

    count: int
    total: int
    mean: float
    median: float
    minimum: int
    maximum: int
    gini: float
    #: Share of total wealth held by the richest 10 % (at least one resident).
    top_10_share: float
    #: Share of total wealth held by the poorest half.
    bottom_50_share: float

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def summarize_wealth(values: Sequence[int]) -> WealthSummary:
    if not values:
        return WealthSummary(0, 0, 0.0, 0.0, 0, 0, 0.0, 0.0, 0.0)
    ranked = sorted(values)
    count = len(ranked)
    total = sum(ranked)
    top = ranked[-max(1, -(-count // 10)) :]
    bottom = ranked[: count // 2]
    return WealthSummary(
        count=count,
        total=total,
        mean=round(total / count, 2),
        median=round(float(statistics.median(ranked)), 2),
        minimum=ranked[0],
        maximum=ranked[-1],
        gini=round(gini(ranked), 4),
        top_10_share=round(sum(top) / total, 4) if total else 0.0,
        bottom_50_share=round(sum(bottom) / total, 4) if total else 0.0,
    )
