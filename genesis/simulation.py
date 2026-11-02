"""The authoritative daily loop.

:meth:`Simulation.step` advances the world by one day in fixed phases:

1. **Decide** - each living resident's agent receives an observation and
   proposes a decision: an activity, an optional occupation change and orders.
2. **Occupations** - requested occupation changes are validated and applied.
3. **Production** - residents who chose to work produce their occupation's resource.
4. **Market** - orders are validated and escrowed, each resource is cleared in
   a uniform-price call auction, and trades settle.
5. **Consumption** - residents consume their daily needs; unmet needs cost
   health, and a resident whose health reaches zero dies.
6. **Bookkeeping** - daily statistics are recorded and invariants are checked.

Agents only propose. Every proposal is validated here, every accepted change is
applied here, and every change to a balance is written to the event log.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import replace

from genesis.agents import Agent, default_agents
from genesis.economy import (
    AuctionResult,
    clear_auction,
    consume_needs,
    daily_weather,
    gini,
    next_reference_price,
    production_output,
    settle_trades,
    validate_orders,
)
from genesis.invariants import assert_invariants
from genesis.models import (
    OCCUPATIONS,
    PRODUCT,
    RESOURCES,
    Activity,
    DailyStats,
    Decision,
    EventKind,
    Observation,
    Occupation,
    Resident,
    Resource,
    Rules,
    plain_map,
)
from genesis.world import World


def occupation_census(residents: Sequence[Resident]) -> dict[Occupation, int]:
    return {occ: sum(1 for resident in residents if resident.occupation is occ) for occ in OCCUPATIONS}


def build_observation(
    world: World,
    resident: Resident,
    rules: Rules,
    population: int,
    census: Mapping[Occupation, int],
) -> Observation:
    """Build what ``resident`` may know today. Mappings are copies, never live state."""
    last_change = resident.last_occupation_change
    return Observation(
        day=world.day,
        resident_id=resident.id,
        name=resident.name,
        occupation=resident.occupation,
        can_change_occupation=last_change is None
        or world.day - last_change >= rules.occupation_cooldown_days,
        health=resident.health,
        cash=resident.cash,
        inventory=dict(resident.inventory),
        skills=dict(resident.skills),
        market={resource: replace(world.market[resource]) for resource in RESOURCES},
        population=population,
        census=dict(census),
        money_supply=world.ledger.money_supply,
        rules=rules,
    )


class Simulation:
    """Runs a world forward one day at a time.

    ``agents`` maps policy names (``Resident.policy``) to agents; by default
    every resident uses the rule-based policy. With ``check_invariants`` (the
    default) the state invariants are verified after every day and a violation
    raises :class:`~genesis.models.InvariantViolation` instead of continuing.
    """

    def __init__(
        self,
        world: World,
        agents: Mapping[str, Agent] | None = None,
        *,
        check_invariants: bool = True,
    ) -> None:
        self.world = world
        self.agents: dict[str, Agent] = default_agents() if agents is None else dict(agents)
        self.check_invariants = check_invariants
        self.rules = Rules.from_config(world.config)
        missing = sorted({resident.policy for resident in world.residents} - set(self.agents))
        if missing:
            raise ValueError(f"no agent registered for policies: {', '.join(missing)}")

    def run(self, days: int) -> list[DailyStats]:
        if days < 0:
            raise ValueError("days must be >= 0")
        return [self.step() for _ in range(days)]

    def step(self) -> DailyStats:
        world = self.world
        world.day += 1
        living = world.living()
        census = occupation_census(living)
        decisions = {resident.id: self._decide(resident, len(living), census) for resident in living}
        for resident in living:
            self._change_occupation(resident, decisions[resident.id].new_occupation)
        produced, workers = self._produce(living, decisions)
        results, rejected_orders = self._trade(living, decisions)
        consumed, unmet, deaths = self._consume(living, decisions)
        stats = self._daily_stats(
            started=len(living),
            workers=workers,
            produced=produced,
            consumed=consumed,
            unmet=unmet,
            results=results,
            rejected_orders=rejected_orders,
            deaths=deaths,
        )
        world.stats.append(stats)
        if self.check_invariants:
            assert_invariants(world)
        return stats

    # --- phase 1: decisions ----------------------------------------------------

    def _decide(self, resident: Resident, population: int, census: Mapping[Occupation, int]) -> Decision:
        """Ask the resident's agent for a decision and normalise its shape.

        Agents are untrusted code: an exception or a malformed return value is
        logged and replaced by the default decision (work, no orders), so one
        faulty agent can never stop the world.
        """
        world = self.world
        observation = build_observation(world, resident, self.rules, population, census)
        try:
            decision = self.agents[resident.policy].decide(observation)
        except Exception as error:  # agents are untrusted: see docstring
            world.record(
                EventKind.AGENT_ERROR, resident_id=resident.id, error=f"{type(error).__name__}: {error}"[:200]
            )
            return Decision()
        if not isinstance(decision, Decision):
            world.record(
                EventKind.AGENT_ERROR,
                resident_id=resident.id,
                error=f"decide() returned {type(decision).__name__}, expected Decision",
            )
            return Decision()
        try:
            activity = Activity(decision.activity)
        except (ValueError, TypeError):
            world.record(
                EventKind.ACTION_REJECTED,
                resident_id=resident.id,
                action="activity",
                reason="invalid_activity",
                value=repr(decision.activity)[:60],
            )
            activity = Activity.WORK
        return replace(decision, activity=activity) if activity is not decision.activity else decision

    # --- phase 2: occupations --------------------------------------------------

    def _change_occupation(self, resident: Resident, requested: object) -> None:
        if requested is None:
            return
        world = self.world
        try:
            occupation = Occupation(requested)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            reason = "invalid_occupation"
        else:
            last_change = resident.last_occupation_change
            if occupation is resident.occupation:
                reason = "already_in_occupation"
            elif last_change is not None and world.day - last_change < world.config.occupation_cooldown_days:
                reason = "occupation_cooldown"
            else:
                world.record(
                    EventKind.OCCUPATION_CHANGED,
                    resident_id=resident.id,
                    previous=str(resident.occupation),
                    occupation=str(occupation),
                )
                resident.occupation = occupation
                resident.last_occupation_change = world.day
                return
        world.record(
            EventKind.ACTION_REJECTED,
            resident_id=resident.id,
            action="change_occupation",
            reason=reason,
            value=repr(requested)[:60],
        )

    # --- phase 3: production ---------------------------------------------------

    def _produce(
        self, living: Sequence[Resident], decisions: Mapping[int, Decision]
    ) -> tuple[dict[Resource, int], int]:
        world = self.world
        weather = daily_weather(world.config, world.rng(world.day, "weather"))
        rng = world.rng(world.day, "production")
        produced = dict.fromkeys(RESOURCES, 0)
        workers = 0
        for resident in living:
            if decisions[resident.id].activity is not Activity.WORK:
                continue
            workers += 1
            resource = PRODUCT[resident.occupation]
            quantity = production_output(resident, world.config, weather[resource], rng)
            resident.inventory[resource] += quantity
            world.ledger.produced[resource] += quantity
            produced[resource] += quantity
            world.record(
                EventKind.PRODUCTION,
                resident_id=resident.id,
                resource=str(resource),
                quantity=quantity,
                occupation=str(resident.occupation),
            )
        return produced, workers

    # --- phase 4: market -------------------------------------------------------

    def _trade(
        self, living: Sequence[Resident], decisions: Mapping[int, Decision]
    ) -> tuple[list[AuctionResult], int]:
        world = self.world
        arrival = list(living)
        world.rng(world.day, "market").shuffle(arrival)  # fair, reproducible time priority
        orders, rejections = validate_orders(
            ((resident, decisions[resident.id].orders) for resident in arrival), world.config
        )
        for rejection in rejections:
            world.record(
                EventKind.ORDER_REJECTED,
                resident_id=rejection.resident_id,
                reason=rejection.reason,
                order=rejection.order,
            )
        residents = {resident.id: resident for resident in world.residents}
        results: list[AuctionResult] = []
        for resource in RESOURCES:
            quote = world.market[resource]
            result = clear_auction(resource, orders, quote.price)
            settle_trades(result.trades, residents)
            for trade in result.trades:
                world.record(
                    EventKind.TRADE,
                    resident_id=trade.buyer_id,
                    counterparty_id=trade.seller_id,
                    resource=str(resource),
                    quantity=trade.quantity,
                    price=trade.price,
                    value=trade.value,
                )
            previous = quote.price
            quote.price = next_reference_price(previous, result, world.config)
            quote.demand, quote.supply, quote.volume = result.demand, result.supply, result.volume
            world.record(
                EventKind.MARKET_CLEARED,
                resource=str(resource),
                previous_price=previous,
                price=quote.price,
                clearing_price=result.clearing_price,
                demand=result.demand,
                supply=result.supply,
                volume=result.volume,
                value=result.value,
                trades=len(result.trades),
                best_bid=result.best_bid,
                best_ask=result.best_ask,
            )
            results.append(result)
        return results, len(rejections)

    # --- phase 5: consumption --------------------------------------------------

    def _consume(
        self, living: Sequence[Resident], decisions: Mapping[int, Decision]
    ) -> tuple[dict[Resource, int], dict[Resource, int], int]:
        world = self.world
        consumed = dict.fromkeys(RESOURCES, 0)
        unmet = dict.fromkeys(RESOURCES, 0)
        deaths = 0
        for resident in living:
            rested = decisions[resident.id].activity is Activity.REST
            outcome = consume_needs(resident, world.config, rested=rested)
            for resource in RESOURCES:
                world.ledger.consumed[resource] += outcome.consumed[resource]
                consumed[resource] += outcome.consumed[resource]
                unmet[resource] += outcome.unmet[resource]
            world.record(
                EventKind.CONSUMPTION,
                resident_id=resident.id,
                consumed=plain_map(outcome.consumed),
                unmet=plain_map(outcome.unmet),
                health_before=outcome.health_before,
                health_after=outcome.health_after,
                rested=rested,
            )
            if outcome.health_after == 0:
                resident.alive = False
                resident.died_on = world.day
                deaths += 1
                # The estate stays with the deceased; inheritance is not modelled in v0.1.
                world.record(
                    EventKind.RESIDENT_DIED,
                    resident_id=resident.id,
                    cause="unmet_needs",
                    estate_cash=resident.cash,
                    estate_inventory=plain_map(resident.inventory),
                )
        return consumed, unmet, deaths

    # --- phase 6: bookkeeping --------------------------------------------------

    def _daily_stats(
        self,
        *,
        started: int,
        workers: int,
        produced: dict[Resource, int],
        consumed: dict[Resource, int],
        unmet: dict[Resource, int],
        results: Sequence[AuctionResult],
        rejected_orders: int,
        deaths: int,
    ) -> DailyStats:
        world = self.world
        living = world.living()
        by_resource = {result.resource: result for result in results}
        wealth = [world.wealth(resident) for resident in living]
        return DailyStats(
            day=world.day,
            population=len(living),
            deaths=deaths,
            working=workers,
            resting=started - workers,
            occupations=occupation_census(living),
            prices=world.prices(),
            production=produced,
            consumption=consumed,
            unmet_needs=unmet,
            demand={resource: by_resource[resource].demand for resource in RESOURCES},
            supply={resource: by_resource[resource].supply for resource in RESOURCES},
            trade_volume={resource: by_resource[resource].volume for resource in RESOURCES},
            trade_value={resource: by_resource[resource].value for resource in RESOURCES},
            trade_count=sum(len(result.trades) for result in results),
            rejected_orders=rejected_orders,
            holdings=world.holdings(),
            money_supply=world.total_cash(),
            mean_health=round(sum(r.health for r in living) / len(living), 2) if living else 0.0,
            total_wealth=sum(wealth),
            gini=round(gini(wealth), 4),
        )
