# The GENESIS v0.1 economy

This document describes exactly what the simulation does, why each rule exists,
and what it deliberately leaves out. The mechanics are intentionally simple.
They are meant to be a transparent, testable baseline, not a realistic model of
any real economy, and nothing here guarantees realistic or "emergent" outcomes.

All quantities are integers: resources in whole units, money in **cents**
(100 cents = 1 credit). All parameters live in `SimulationConfig`
([genesis/models.py](../genesis/models.py)) and `RuleBasedAgent`
([genesis/agents.py](../genesis/agents.py)).

## The world

| Element | Default |
| --- | --- |
| Residents | 20 |
| Resources | food, wood, stone |
| Occupations | farmer -> food, woodcutter -> wood, miner -> stone |
| Base output per working day | farmer 5, woodcutter 4, miner 3 units |
| Skill per occupation | drawn uniformly from 75-125 % at creation |
| Starting occupation | the one the resident is most skilled at |
| Starting endowment | 100.00 credits and 5 units of each resource |
| Opening reference prices | food 3.00, wood 4.00, stone 5.00 credits |
| Daily needs | 1 food, 1 wood, 1 stone per resident |
| Health | 0-100; a resident whose health reaches 0 dies |

There is no money creation or destruction in v0.1: the money supply is fixed at
creation (`20 x 100.00 = 2,000.00` credits by default).

## A day, phase by phase

The engine ([genesis/simulation.py](../genesis/simulation.py)) is authoritative.
Agents only propose; the engine validates, executes and records.

1. **Decide.** Each living resident's agent receives an `Observation` (its own
   state, public market quotes, the occupation census, the money supply and the
   published rules) and returns a `Decision`: an activity (`work` or `rest`), an
   optional occupation change, and limit orders.
2. **Occupation changes.** Valid if the occupation exists, differs from the
   current one, and at least `occupation_cooldown_days` (7) have passed since the
   resident's last change. Changes take effect before today's work.
3. **Production.** Each resident who works produces
   `base_output x skill% x vitality% x weather%` units of their product, where
   vitality falls linearly from 100 % at full health to 75 % at zero health and
   weather is a daily per-resource shock drawn from 90-110 %. Fractions are
   resolved by stochastic rounding, so outputs are integers whose average equals
   the expectation.
4. **Market.** See below.
5. **Consumption.** Each resident consumes their daily needs from their own
   inventory. Every missing unit costs health (food 20, wood 5, stone 3). A day
   with every need met restores 5 health; a rest day restores 5 more. Health is
   clamped to 0-100 and a resident at 0 dies.
6. **Bookkeeping.** Daily statistics are recorded and the invariants are checked.

## The market: a daily uniform-price call auction

Every resource has one auction per day ([genesis/economy.py](../genesis/economy.py)).

**Validation and escrow.** Orders are processed in a reproducibly shuffled
arrival order. A buy order must be backed by unreserved cash for
`quantity x limit_price`; a sell order by unreserved inventory. A resident may
not buy and sell the same resource on the same day, may place at most 10 orders
per day, and quantities and prices must be positive integers within bounds.
Rejected orders are logged with a reason. Because everything is reserved up
front, all accepted orders can settle at once and no balance can go negative.
The price of this simplicity is that proceeds from today's sales can only be
spent tomorrow.

**Clearing price.** Standard call-auction rules, in order: maximise volume;
minimise the leftover imbalance; if only buyers are left over take the highest
such price, if only sellers the lowest (market pressure); otherwise the price
closest to yesterday's reference price.

**Allocation.** Better-priced orders fill first. Orders at the marginal price
share what is left **pro rata** to their size, with rounding leftovers going to
the earliest arrivals. Every trade executes at the single clearing price, which
never exceeds a matched buyer's limit nor falls below a matched seller's.

**Reference price.** After a trade, the clearing price. Without a trade it moves
5 % up (only buyers), 5 % down (only sellers) or toward the middle of the spread
(both sides, no cross), so prices keep signalling scarcity even on days with no
trades.

## The rule-based resident

`RuleBasedAgent` is stateless and deterministic. Each day it:

1. **Reviews its occupation** once a week, on a day staggered by resident id.
   It never leaves an occupation that has no more workers than the town needs
   (`workers_needed`: everyone's daily need divided by the base output). A
   surplus worker moves to the most understaffed occupation, or else to the one
   with the highest expected income (its share of demand times the price) if
   that beats its current income by 5 % of a day's living cost.
2. **Buys** every resource it holds less than 5 days of needs of, never its own
   product. It budgets today's needs of every resource before topping up any
   buffer, never commits more cash than it has, and bids a premium over the
   reference price that grows with urgency (2 %, 6 %, or 15 % when out of stock).
3. **Sells** its surplus beyond the buffer, at most one day of output per day.
   It discounts (1-6 %, more for larger stocks) only while goods are expensive
   relative to money, that is while the money supply covers fewer than 10 days
   of the town's needs; otherwise it asks the reference price. It never asks
   less than 90 % of its break-even price (the price at which its expected sales
   pay for the other needs it must buy) but raises its ask above the reference
   price by at most 5 % a day.
4. **Rests** while it holds 20 days of needs of its own product.

### Why these rules

Earlier, simpler versions failed in instructive ways, and each rule above fixes
one failure that was observed in multi-seed runs:

| Failure observed | Rule that fixes it |
| --- | --- |
| Herding: everyone switched to the best-paid occupation at once, production of something essential stopped, everyone died | staggered reviews, "never leave if needed", estimates that count the switcher as one more producer |
| Deflation spiral: sellers undercut each other in every glut until prices reached 1 cent | sellers stop undercutting once goods are cheap relative to the fixed money supply |
| Producers of a crowded good went broke: a fixed demand split among many sellers cannot feed them at a falling price | break-even price floors, plus moving surplus workers out |
| Inflation spiral when floors were set at 100 % of break-even | floors at 90 %, which leaves the price system slack |
| Unlucky sellers starved because random rationing gave them no sales for days | pro-rata allocation at the marginal price |
| Residents with cash went without wood because they spent everything on a 5-day food buffer first | two-pass budgeting: today's needs first |

## What the default world does

Measured on seeds 42 and 1-10 (reproduce with `python main.py demo --seed N --days N`):

- **100 days:** all 11 worlds keep all 20 residents alive; unmet needs stay
  below 2 % of required units; the Gini coefficient of wealth ends between 0.13
  and 0.34; prices stay within about 25 % of their opening levels.
- **365 days:** 18-20 residents survive; inequality keeps rising (Gini 0.24-0.49).

These are properties of this configuration and policy, not guarantees. Other
seeds, parameters or policies can and do produce shortages, poverty and deaths;
the engine handles all of them, and the invariants hold regardless.

## Known limitations

- **Prices are sticky.** Once goods are cheap relative to money, nobody
  undercuts, so in the default world prices settle within about ten days and then
  move only when a real shortage appears. This is a policy property, not an
  engine one: other agents can bid and ask whatever they like.
- **Inequality drifts upward.** Workers in uncrowded occupations earn slightly
  more than they spend; workers in crowded ones slightly less, because floors sit
  10 % below break-even. With no investment, credit, taxes, transfers or
  inheritance, money slowly accumulates with the former, and over a year a few
  of the poorest can die.
- **Demand is perfectly inelastic.** Residents need exactly one unit of each
  resource per day and want nothing beyond a buffer. There are no luxuries,
  substitutes or durable goods.
- **No capital, credit, wages or firms.** Everyone is self-employed and
  production needs only labour.
- **No births, ageing or inheritance.** The population can only shrink, and the
  estates of the dead stay frozen in place (still counted in totals).
- **T+1 settlement.** Proceeds from a sale can be spent the next day.
- **One shared market**, no geography, transport or storage costs, no spoilage.
- **Agents are not optimisers.** The rule-based policy is a transparent
  heuristic, not a utility maximiser.

## Experimenting

Change any parameter through `SimulationConfig` or `RuleBasedAgent`, or plug in
a different policy:

```python
from dataclasses import replace
from genesis.agents import RuleBasedAgent
from genesis.models import SimulationConfig
from genesis.simulation import Simulation
from genesis.world import create_world

config = replace(SimulationConfig(), base_output={"farmer": 4, "woodcutter": 4, "miner": 3})
world = create_world(config, seed=7)
Simulation(world, {"rule_based": RuleBasedAgent(buffer_days=3)}).run(200)
print(world.stats[-1].population, world.stats[-1].prices)
```
