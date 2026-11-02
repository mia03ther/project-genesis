"""Accounting and consistency invariants.

:func:`check_invariants` covers the state itself and is cheap; the simulation
runs it after every day. :func:`audit_event_log` is an independent second
opinion: it replays every recorded state change from the genesis allocation and
must arrive at exactly the current balances. Together they establish that

- no holding is ever negative (also at every intermediate step of the replay),
- money is conserved: no mechanism creates or destroys cash,
- resources are conserved: holdings == initial + produced - consumed,
- every trade moves equal value in both directions at its auction's price,
- the event log is a complete record of every change to a balance.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field

from genesis.models import MAX_HEALTH, RESOURCES, EventKind, InvariantViolation, Resource
from genesis.world import World


@dataclass
class _AuctionTally:
    """Trades seen so far for one (day, resource) auction during an audit."""

    volume: int = 0
    value: int = 0
    trades: int = 0
    prices: set[int] = field(default_factory=set)


def _subject(resident_id: int | None) -> int:
    if resident_id is None:
        raise ValueError("event has no resident_id")
    return resident_id


def check_invariants(world: World) -> list[str]:
    """Return a description of every violated state invariant (empty when all hold)."""
    problems: list[str] = []
    config = world.config
    ids = [resident.id for resident in world.residents]
    if ids != list(range(1, len(ids) + 1)):
        problems.append("resident ids must be 1..N in order")
    for resident in world.residents:
        label = f"resident {resident.id}"
        if resident.cash < 0:
            problems.append(f"{label} has negative cash ({resident.cash})")
        if set(resident.inventory) != set(RESOURCES):
            problems.append(f"{label} inventory must list exactly {[str(r) for r in RESOURCES]}")
            continue
        for resource in RESOURCES:
            if resident.inventory[resource] < 0:
                problems.append(f"{label} holds negative {resource} ({resident.inventory[resource]})")
        if not 0 <= resident.health <= MAX_HEALTH:
            problems.append(f"{label} health {resident.health} is outside 0..{MAX_HEALTH}")
        if resident.alive != (resident.health > 0):
            problems.append(f"{label} is alive={resident.alive} with health {resident.health}")
        if resident.alive != (resident.died_on is None):
            problems.append(f"{label} is alive={resident.alive} but died_on={resident.died_on}")

    total_cash = world.total_cash()
    if total_cash != world.ledger.money_supply:
        problems.append(
            f"currency not conserved: residents hold {total_cash} cents, money supply is {world.ledger.money_supply}"
        )
    holdings = world.holdings()
    for resource in RESOURCES:
        expected = world.ledger.expected_holdings(resource)
        if holdings[resource] != expected:
            problems.append(
                f"{resource} not conserved: residents hold {holdings[resource]}, "
                f"initial + produced - consumed = {expected}"
            )
    for resource in RESOURCES:
        price = world.market[resource].price
        if not config.min_price <= price <= config.max_price:
            problems.append(f"{resource} price {price} is outside {config.min_price}..{config.max_price}")
    if world.events and world.events[-1].seq != len(world.events):
        problems.append("event sequence numbers are not contiguous")
    if world.stats and world.stats[-1].day != world.day:
        problems.append(f"latest daily stats are for day {world.stats[-1].day}, world is at day {world.day}")
    return problems


def audit_event_log(world: World) -> list[str]:
    """Replay the event log and compare the outcome with the current state.

    Returns a description of every discrepancy (empty when the log and the
    state agree). The replay only uses events, never the state it checks.
    """
    problems: list[str] = []
    cash: dict[int, int] = {}
    stock: dict[int, dict[Resource, int]] = {}
    produced = dict.fromkeys(RESOURCES, 0)
    consumed = dict.fromkeys(RESOURCES, 0)
    auctions: dict[tuple[int, str], _AuctionTally] = defaultdict(_AuctionTally)
    last_day = 0

    def debit_check(seq: int, resident_id: int) -> None:
        if cash[resident_id] < 0:
            problems.append(f"event {seq}: resident {resident_id} cash went negative")
        for resource in RESOURCES:
            if stock[resident_id][resource] < 0:
                problems.append(f"event {seq}: resident {resident_id} {resource} went negative")

    for expected_seq, event in enumerate(world.events, start=1):
        if event.seq != expected_seq:
            problems.append(f"event {expected_seq} has sequence number {event.seq}")
            return problems
        if event.day < last_day:
            problems.append(f"event {event.seq} goes back in time to day {event.day}")
        last_day = event.day
        data = event.data
        try:
            if event.kind is EventKind.RESIDENT_CREATED:
                rid = _subject(event.resident_id)
                if rid in cash:
                    problems.append(f"event {event.seq}: resident {rid} created twice")
                cash[rid] = data["cash"]
                stock[rid] = {r: data["inventory"][str(r)] for r in RESOURCES}
            elif event.kind is EventKind.PRODUCTION:
                rid = _subject(event.resident_id)
                resource = Resource(data["resource"])
                if data["quantity"] < 0:
                    problems.append(f"event {event.seq}: negative production")
                stock[rid][resource] += data["quantity"]
                produced[resource] += data["quantity"]
            elif event.kind is EventKind.CONSUMPTION:
                rid = _subject(event.resident_id)
                for resource in RESOURCES:
                    used = data["consumed"][str(resource)]
                    stock[rid][resource] -= used
                    consumed[resource] += used
                debit_check(event.seq, rid)
            elif event.kind is EventKind.TRADE:
                buyer, seller = _subject(event.resident_id), _subject(event.counterparty_id)
                resource = Resource(data["resource"])
                quantity, price, value = data["quantity"], data["price"], data["value"]
                if buyer == seller:
                    problems.append(f"event {event.seq}: resident {buyer} traded with themself")
                if quantity <= 0 or not world.config.min_price <= price <= world.config.max_price:
                    problems.append(f"event {event.seq}: invalid trade quantity or price")
                if value != quantity * price:
                    problems.append(f"event {event.seq}: trade value {value} != {quantity} x {price}")
                cash[buyer] -= value
                cash[seller] += value
                stock[seller][resource] -= quantity
                stock[buyer][resource] += quantity
                debit_check(event.seq, buyer)
                debit_check(event.seq, seller)
                tally = auctions[(event.day, str(resource))]
                tally.volume += quantity
                tally.value += value
                tally.trades += 1
                tally.prices.add(price)
            elif event.kind is EventKind.MARKET_CLEARED:
                tally = auctions.pop((event.day, data["resource"]), _AuctionTally())
                if (tally.volume, tally.value, tally.trades) != (
                    data["volume"],
                    data["value"],
                    data["trades"],
                ):
                    problems.append(f"event {event.seq}: market summary does not match its trades")
                if tally.prices and tally.prices != {data["clearing_price"]}:
                    problems.append(f"event {event.seq}: trades did not all execute at the clearing price")
        except (KeyError, TypeError, ValueError) as error:
            problems.append(f"event {event.seq} ({event.kind}) is malformed: {error!r}")

    if auctions:
        problems.append(f"trades without a market summary: {sorted(auctions)}")
    if sum(cash.values()) != world.ledger.money_supply:
        problems.append("genesis allocation does not match the money supply")
    for resident in world.residents:
        if resident.id not in cash:
            problems.append(f"resident {resident.id} has no creation event")
            continue
        if cash[resident.id] != resident.cash:
            problems.append(f"resident {resident.id} cash {resident.cash} != replayed {cash[resident.id]}")
        for resource in RESOURCES:
            if stock[resident.id][resource] != resident.inventory[resource]:
                problems.append(
                    f"resident {resident.id} {resource} {resident.inventory[resource]} "
                    f"!= replayed {stock[resident.id][resource]}"
                )
    for resource in RESOURCES:
        if produced[resource] != world.ledger.produced[resource]:
            problems.append(
                f"ledger produced {resource} {world.ledger.produced[resource]} != events {produced[resource]}"
            )
        if consumed[resource] != world.ledger.consumed[resource]:
            problems.append(
                f"ledger consumed {resource} {world.ledger.consumed[resource]} != events {consumed[resource]}"
            )
    return problems


def assert_invariants(world: World, *, audit: bool = False) -> None:
    """Raise :class:`InvariantViolation` listing every violated invariant."""
    problems = check_invariants(world)
    if audit:
        problems += audit_event_log(world)
    if problems:
        shown = "; ".join(problems[:10])
        more = f" (+{len(problems) - 10} more)" if len(problems) > 10 else ""
        raise InvariantViolation(shown + more)
