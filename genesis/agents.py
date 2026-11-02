"""The agent decision interface and the built-in rule-based policy.

An agent is any object with a ``decide(observation) -> Decision`` method. Agents
only *propose*: they never receive the world, and the engine validates every
proposal before applying it. That boundary is what lets a future adapter for a
language model (Claude, GPT, Gemini, ...) plug in without engine changes: the
adapter renders ``observation.to_dict()`` into a prompt, parses the reply with
``Decision.from_dict`` and returns the result. Anything invalid in the reply is
rejected and logged by the engine like any other bad proposal.

Agents should be deterministic functions of their observation. Randomness or
hidden state inside an agent would break reproducible replays from a seed.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from genesis.models import (
    DEFAULT_POLICY,
    OCCUPATIONS,
    RESOURCES,
    Activity,
    Decision,
    Observation,
    Occupation,
    OrderRequest,
    Resource,
    Side,
)

BPS = 10_000


class Agent(Protocol):
    """Anything that can turn an observation into a proposed decision."""

    def decide(self, observation: Observation) -> Decision: ...


# --- estimates every resident can compute from public information --------------


def living_cost(observation: Observation) -> int:
    """Cents needed to buy one full day of needs at today's reference prices."""
    rules = observation.rules
    return sum(rules.daily_needs[r] * observation.market[r].price for r in RESOURCES)


def workers_needed(observation: Observation, occupation: Occupation) -> int:
    """Workers of average (100 %) skill needed to cover everyone's daily need
    for the occupation's product."""
    rules = observation.rules
    output = rules.base_output[occupation]
    if output == 0:
        return 0
    demand = rules.daily_needs[rules.products[occupation]] * observation.population
    return -(-demand // output)


def expected_sales(observation: Observation, occupation: Occupation) -> int:
    """Units (x 100) of product a worker in ``occupation`` can expect to sell per day.

    That is the worker's output beyond their own need, capped by an equal share
    of what the other residents need. For an occupation the resident does not
    have, the share counts them as one more producer, so the estimate already
    includes the effect of switching.
    """
    rules = observation.rules
    product = rules.products[occupation]
    producers = max(1, observation.census[occupation] + (0 if occupation is observation.occupation else 1))
    need = rules.daily_needs[product] * 100
    surplus = max(0, rules.base_output[occupation] * observation.skills[occupation] - need)
    share = rules.daily_needs[product] * max(0, observation.population - producers) * 100 // producers
    return min(surplus, share)


def expected_income(observation: Observation, occupation: Occupation) -> int:
    """Expected daily sales revenue of working ``occupation``, in cents x 100."""
    product = observation.rules.products[occupation]
    return expected_sales(observation, occupation) * observation.market[product].price


def break_even_price(observation: Observation, occupation: Occupation) -> int:
    """Price at which a worker's :func:`expected_sales` pay for the other needs they buy.

    A fixed demand split among many sellers only keeps them all fed at a
    higher price, so the break-even price of a crowded occupation is high;
    the crowding itself is resolved when surplus workers move elsewhere.
    """
    rules = observation.rules
    product = rules.products[occupation]
    expenses = sum(rules.daily_needs[r] * observation.market[r].price for r in RESOURCES if r is not product)
    return -(-expenses * 100 // max(1, expected_sales(observation, occupation)))


def money_cover_days(observation: Observation) -> int:
    """Days of the whole population's needs the money supply buys at current prices.

    A public measure of the price level: the higher it is, the cheaper goods
    are relative to the (fixed) amount of money.
    """
    return observation.money_supply // max(1, observation.population * living_cost(observation))


# --- the built-in policy ----------------------------------------------------------


@dataclass(frozen=True, slots=True)
class RuleBasedAgent:
    """A transparent, needs-driven policy. Stateless and deterministic.

    Each day the agent:

    1. **Reviews its occupation** once every ``review_interval_days``, on a day
       staggered by resident id so the population never switches in lockstep.
       It stays while its occupation has no more workers than the town needs
       (:func:`workers_needed`). A surplus worker moves to the most understaffed
       occupation, or else to the one with the highest :func:`expected_income`
       if that beats its current income by ``switch_margin_pct`` of a day's
       living cost.
    2. **Buys** every resource it holds less than ``buffer_days`` of needs of,
       most vital need first, never committing more cash than it has. It bids a
       premium over the reference price that grows with urgency. It does not
       buy its own product, which today's work will provide.
    3. **Sells** surplus of its own product beyond the buffer, at most one day
       of expected output per day; other resources are sold beyond twice the
       buffer. It discounts the reference price, more so the larger its stock,
       but only while the money supply covers fewer than ``anchor_days`` of
       the town's needs (:func:`money_cover_days`): once goods are cheap
       relative to money, sellers stop undercutting, which anchors the price
       level. It never asks below ``floor_pct`` of its :func:`break_even_price`,
       but raises its ask above the reference price by at most
       ``max_markup_bps`` per day.
    4. **Rests** instead of working while it holds ``overstock_days`` of needs
       of its own product, so unsold stock clears before it produces more.
    """

    buffer_days: int = 5
    overstock_days: int = 20
    anchor_days: int = 10
    floor_pct: int = 90
    review_interval_days: int = 7
    switch_margin_pct: int = 5
    urgent_premium_bps: int = 1_500
    low_premium_bps: int = 600
    normal_premium_bps: int = 200
    discount_bps: int = 100
    surplus_discount_bps: int = 300
    glut_discount_bps: int = 600
    max_markup_bps: int = 500

    def __post_init__(self) -> None:
        if self.buffer_days < 1 or self.overstock_days < self.buffer_days or self.review_interval_days < 1:
            raise ValueError("invalid RuleBasedAgent parameters")

    def decide(self, observation: Observation) -> Decision:
        new_occupation = self._review_occupation(observation)
        occupation = observation.occupation if new_occupation is None else new_occupation
        product = observation.rules.products[occupation]
        orders = self._buy_orders(observation, product) + self._sell_orders(observation, occupation)
        overstock = max(1, observation.rules.daily_needs[product] * self.overstock_days)
        return Decision(
            activity=Activity.REST if observation.inventory[product] >= overstock else Activity.WORK,
            orders=tuple(orders),
            new_occupation=new_occupation,
        )

    def _review_occupation(self, observation: Observation) -> Occupation | None:
        if not observation.can_change_occupation:
            return None
        if (observation.day + observation.resident_id) % self.review_interval_days != 0:
            return None
        current = observation.occupation
        census = observation.census
        if census[current] <= workers_needed(observation, current):
            return None  # every worker here is needed to cover the town's needs
        shortfall = {occ: workers_needed(observation, occ) - census[occ] for occ in OCCUPATIONS}
        income = {occ: expected_income(observation, occ) for occ in OCCUPATIONS}
        understaffed = [occ for occ in OCCUPATIONS if shortfall[occ] > 0]
        if understaffed:
            return max(understaffed, key=lambda occ: (shortfall[occ], income[occ]))
        best = max(OCCUPATIONS, key=lambda occ: income[occ])
        # income is in cents x 100, so "pct of living cost" needs no further scaling
        if income[best] - income[current] > self.switch_margin_pct * living_cost(observation):
            return best
        return None

    def _buy_orders(self, observation: Observation, product: Resource) -> list[OrderRequest]:
        rules = observation.rules
        wanted: list[tuple[Resource, int, int, int]] = []  # (resource, limit, today's shortfall, buffer gap)
        # Most damaging unmet need first; the sort is stable, so ties keep canonical order.
        for resource in sorted(RESOURCES, key=lambda r: -rules.unmet_need_penalty[r]):
            if resource is product:
                continue
            need = rules.daily_needs[resource]
            stock = observation.inventory[resource]
            target = need * self.buffer_days
            if stock >= target:
                continue
            if stock < need:
                premium = self.urgent_premium_bps
            elif stock * 2 < target:
                premium = self.low_premium_bps
            else:
                premium = self.normal_premium_bps
            limit = _bounded(-(-observation.market[resource].price * (BPS + premium) // BPS), observation)
            wanted.append((resource, limit, max(0, need - stock), target - stock))

        # Budget in two passes: first today's needs of every resource, then buffers.
        budget = observation.cash
        quantities: dict[Resource, int] = {}
        for pass_index in (0, 1):
            for resource, limit, shortfall, gap in wanted:
                have = quantities.get(resource, 0)
                goal = shortfall if pass_index == 0 else gap
                quantity = max(0, min(goal - have, budget // limit, rules.max_order_quantity - have))
                quantities[resource] = have + quantity
                budget -= quantity * limit
        return [
            OrderRequest(Side.BUY, resource, quantities[resource], limit)
            for resource, limit, _, _ in wanted
            if quantities[resource] > 0
        ]

    def _sell_orders(self, observation: Observation, occupation: Occupation) -> list[OrderRequest]:
        rules = observation.rules
        product = rules.products[occupation]
        prices_high = money_cover_days(observation) < self.anchor_days
        floor = break_even_price(observation, occupation) * self.floor_pct // 100
        orders: list[OrderRequest] = []
        for resource in RESOURCES:
            stock = observation.inventory[resource]
            target = rules.daily_needs[resource] * self.buffer_days
            if resource is product:
                pace = max(1, rules.base_output[occupation] * observation.skills[occupation] // 100)
                quantity = min(stock - target, pace)
            elif stock > 2 * target:
                quantity = stock - target
            else:
                continue
            if quantity <= 0:
                continue
            reference = observation.market[resource].price
            if not prices_high:
                discount = 0
            elif stock >= 3 * target:
                discount = self.glut_discount_bps
            elif stock >= 2 * target:
                discount = self.surplus_discount_bps
            else:
                discount = self.discount_bps
            limit = reference * (BPS - discount) // BPS
            if resource is product:
                ceiling = reference * (BPS + self.max_markup_bps) // BPS
                limit = max(limit, min(floor, ceiling))
            quantity = min(quantity, rules.max_order_quantity)
            orders.append(OrderRequest(Side.SELL, resource, quantity, _bounded(limit, observation)))
        return orders


def _bounded(price: int, observation: Observation) -> int:
    return max(observation.rules.min_price, min(observation.rules.max_price, price))


def default_agents() -> dict[str, Agent]:
    """Policies available to every simulation, keyed by ``Resident.policy``."""
    return {DEFAULT_POLICY: RuleBasedAgent()}
