"""Human-readable summaries and machine-readable experiment reports."""

from __future__ import annotations

import csv
import json
import os
from pathlib import Path
from typing import Any

from genesis import __version__
from genesis.economy import WealthSummary, summarize_wealth
from genesis.models import OCCUPATIONS, RESOURCES, DailyStats, EventKind, Resource, plain_map
from genesis.world import World

REPORT_FORMAT = "genesis.report"
REPORT_VERSION = 1
CSV_TABLES = ("daily", "residents", "trades")


def format_money(cents: int) -> str:
    """Render integer cents as credits, e.g. ``123456 -> '1,234.56'``."""
    sign = "-" if cents < 0 else ""
    whole, fraction = divmod(abs(cents), 100)
    return f"{sign}{whole:,}.{fraction:02d}"


def trade_totals(world: World) -> dict[str, Any]:
    """Trades, units and value (cents) since day 1, overall and per resource."""
    units = dict.fromkeys(RESOURCES, 0)
    value = dict.fromkeys(RESOURCES, 0)
    count = 0
    for stats in world.stats:
        count += stats.trade_count
        for resource in RESOURCES:
            units[resource] += stats.trade_volume[resource]
            value[resource] += stats.trade_value[resource]
    return {
        "trades": count,
        "units": sum(units.values()),
        "value": sum(value.values()),
        "units_by_resource": plain_map(units),
        "value_by_resource": plain_map(value),
    }


def wealth_summary(world: World) -> WealthSummary:
    """Wealth distribution of the living residents."""
    return summarize_wealth([world.wealth(resident) for resident in world.living()])


def world_summary(world: World) -> dict[str, Any]:
    living = world.living()
    estates = [resident for resident in world.residents if not resident.alive]
    all_holdings = world.holdings()
    living_holdings = world.holdings(living_only=True)
    return {
        "day": world.day,
        "seed": world.seed,
        "population": {"alive": len(living), "dead": len(estates), "total": len(world.residents)},
        "occupations": {str(occ): sum(1 for r in living if r.occupation is occ) for occ in OCCUPATIONS},
        "prices": plain_map(world.prices()),
        "holdings": {
            "total": plain_map(all_holdings),
            "living": plain_map(living_holdings),
            "estates": {str(r): all_holdings[r] - living_holdings[r] for r in RESOURCES},
        },
        "money_supply": world.ledger.money_supply,
        "cash": {"living": sum(r.cash for r in living), "estates": sum(r.cash for r in estates)},
        "produced": plain_map(world.ledger.produced),
        "consumed": plain_map(world.ledger.consumed),
        "trades": trade_totals(world),
        "mean_health": round(sum(r.health for r in living) / len(living), 2) if living else 0.0,
        "wealth": wealth_summary(world).to_dict(),
        "events": len(world.events),
        "state_digest": world.state_digest(),
    }


def resident_rows(world: World) -> list[dict[str, Any]]:
    return [
        {
            "id": r.id,
            "name": r.name,
            "occupation": str(r.occupation),
            "alive": r.alive,
            "died_on": r.died_on,
            "health": r.health,
            "cash": r.cash,
            **{str(res): r.inventory[res] for res in RESOURCES},
            "wealth": world.wealth(r),
            **{f"skill_{occ}": r.skills[occ] for occ in OCCUPATIONS},
            "policy": r.policy,
        }
        for r in world.residents
    ]


def flatten_stats(stats: DailyStats) -> dict[str, Any]:
    """One flat row per day, for CSV and spreadsheets."""
    row: dict[str, Any] = {
        "day": stats.day,
        "population": stats.population,
        "deaths": stats.deaths,
        "working": stats.working,
        "resting": stats.resting,
    }
    for occ in OCCUPATIONS:
        row[f"{occ}s"] = stats.occupations[occ]
    for name in ("prices", "production", "consumption", "unmet_needs", "demand", "supply",
                 "trade_volume", "trade_value", "holdings"):  # fmt: skip
        values = getattr(stats, name)
        for resource in RESOURCES:
            row[f"{resource}_{name}"] = values[resource]
    row.update(
        trade_count=stats.trade_count,
        rejected_orders=stats.rejected_orders,
        money_supply=stats.money_supply,
        mean_health=stats.mean_health,
        total_wealth=stats.total_wealth,
        gini=stats.gini,
    )
    return row


def trade_rows(world: World) -> list[dict[str, Any]]:
    return [
        {
            "seq": e.seq,
            "day": e.day,
            "resource": e.data["resource"],
            "buyer_id": e.resident_id,
            "seller_id": e.counterparty_id,
            "quantity": e.data["quantity"],
            "price": e.data["price"],
            "value": e.data["value"],
        }
        for e in world.events
        if e.kind is EventKind.TRADE
    ]


def build_report(world: World) -> dict[str, Any]:
    """A self-describing experiment report. Deterministic: no timestamps."""
    return {
        "format": REPORT_FORMAT,
        "report_version": REPORT_VERSION,
        "genesis_version": __version__,
        "world": {"seed": world.seed, "day": world.day, "config": world.config.to_dict()},
        "summary": world_summary(world),
        "residents": resident_rows(world),
        "daily": [flatten_stats(stats) for stats in world.stats],
    }


def write_report(world: World, path: str | os.PathLike[str], fmt: str = "json", table: str = "daily") -> Path:
    """Write a JSON report, or one CSV table (``daily``, ``residents`` or ``trades``)."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    if fmt == "json":
        target.write_text(json.dumps(build_report(world), indent=2) + "\n", encoding="utf-8")
        return target
    if fmt != "csv":
        raise ValueError(f"unknown report format {fmt!r}; use 'json' or 'csv'")
    if table == "daily":
        rows = [flatten_stats(stats) for stats in world.stats]
    elif table == "residents":
        rows = resident_rows(world)
    elif table == "trades":
        rows = trade_rows(world)
    else:
        raise ValueError(f"unknown CSV table {table!r}; use one of {', '.join(CSV_TABLES)}")
    with target.open("w", newline="", encoding="utf-8") as handle:
        if rows:
            writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
    return target


# --- text rendering -----------------------------------------------------------


def _resource_line(values: dict[Resource, int] | dict[str, int], money: bool = False) -> str:
    parts = []
    for resource in RESOURCES:
        value = values[resource]
        parts.append(f"{resource} {format_money(value) if money else f'{value:,}'}")
    return "  ".join(parts)


def render_wealth(summary: WealthSummary) -> list[str]:
    if summary.count == 0:
        return ["Wealth: nobody is alive"]
    return [
        "Wealth of living residents (cash + inventory at market prices, credits):",
        f"  mean {format_money(round(summary.mean))}  median {format_money(round(summary.median))}"
        f"  min {format_money(summary.minimum)}  max {format_money(summary.maximum)}",
        f"  Gini {summary.gini:.3f}  richest 10% hold {summary.top_10_share:.1%}"
        f"  poorest 50% hold {summary.bottom_50_share:.1%}",
    ]


def render_status(world: World, source: str | None = None) -> str:
    living = world.living()
    dead = len(world.residents) - len(living)
    totals = trade_totals(world)
    holdings = world.holdings()
    living_holdings = world.holdings(living_only=True)
    occupations = "  ".join(f"{occ} {sum(1 for r in living if r.occupation is occ)}" for occ in OCCUPATIONS)
    lines = [
        f"GENESIS world - day {world.day}, seed {world.seed}" + (f" ({source})" if source else ""),
        f"Population: {len(living)} alive, {dead} dead (of {len(world.residents)})",
        f"Occupations: {occupations}",
        f"Market prices (credits/unit): {_resource_line(world.prices(), money=True)}",
        f"Resources held, all residents: {_resource_line(holdings)}",
        f"Resources held, living only:   {_resource_line(living_holdings)}",
        f"Produced to date: {_resource_line(world.ledger.produced)}",
        f"Consumed to date: {_resource_line(world.ledger.consumed)}",
        f"Money supply: {format_money(world.ledger.money_supply)} credits (constant; "
        f"{format_money(sum(r.cash for r in living))} held by the living)",
        f"Transactions: {totals['trades']:,} trades, {totals['units']:,} units, "
        f"{format_money(totals['value'])} credits",
        *render_wealth(wealth_summary(world)),
        f"Mean health of the living: {sum(r.health for r in living) / len(living):.1f}" if living else "",
        f"Event log: {len(world.events):,} events   State digest: {world.state_digest()[:16]}",
    ]
    return "\n".join(line for line in lines if line)


def render_residents(world: World, sort_by: str = "id") -> str:
    keys = {
        "id": lambda r: r.id,
        "name": lambda r: r.name,
        "wealth": lambda r: -world.wealth(r),
        "cash": lambda r: -r.cash,
        "health": lambda r: -r.health,
        "occupation": lambda r: (str(r.occupation), r.id),
    }
    if sort_by not in keys:
        raise ValueError(f"cannot sort by {sort_by!r}; use one of {', '.join(keys)}")
    header = f"{'id':>3}  {'name':<10} {'occupation':<10} {'status':<8} {'health':>6} {'cash':>10}"
    header += "".join(f" {res!s:>6}" for res in RESOURCES) + f" {'wealth':>10}"
    lines = [header, "-" * len(header)]
    for r in sorted(world.residents, key=keys[sort_by]):
        status = "alive" if r.alive else f"died d{r.died_on}"
        row = f"{r.id:>3}  {r.name:<10} {r.occupation!s:<10} {status:<8} {r.health:>6} {format_money(r.cash):>10}"
        row += (
            "".join(f" {r.inventory[res]:>6}" for res in RESOURCES) + f" {format_money(world.wealth(r)):>10}"
        )
        lines.append(row)
    return "\n".join(lines)


def render_resident(world: World, resident_id: int, recent: int = 10) -> str:
    r = world.resident(resident_id)
    ranked = sorted(world.living(), key=lambda x: -world.wealth(x))
    rank = next((i for i, x in enumerate(ranked, start=1) if x.id == r.id), None)
    skills = "  ".join(f"{occ} {r.skills[occ]}%" for occ in OCCUPATIONS)
    since = "since creation" if r.last_occupation_change is None else f"since day {r.last_occupation_change}"
    lines = [
        f"Resident {r.id}: {r.name}",
        f"  status      {'alive' if r.alive else f'died on day {r.died_on}'}   health {r.health}/100",
        f"  occupation  {r.occupation} ({since}), policy {r.policy}",
        f"  skills      {skills}",
        f"  cash        {format_money(r.cash)} credits",
        f"  inventory   {_resource_line(r.inventory)}",
        f"  wealth      {format_money(world.wealth(r))} credits"
        + (f" (rank {rank} of {len(ranked)} living)" if rank else ""),
    ]
    events = [e for e in world.events if r.id in (e.resident_id, e.counterparty_id)]
    if recent > 0 and events:
        lines.append(f"  last {min(recent, len(events))} of {len(events)} events:")
        lines.extend(f"    {_describe_event(e, r.id)}" for e in events[-recent:])
    return "\n".join(lines)


def _describe_event(event: Any, resident_id: int) -> str:
    d = event.data
    prefix = f"day {event.day:>4} #{event.seq:<6}"
    match event.kind:
        case EventKind.TRADE:
            role = "bought" if event.resident_id == resident_id else "sold"
            other = event.counterparty_id if role == "bought" else event.resident_id
            text = f"{role} {d['quantity']} {d['resource']} @ {format_money(d['price'])} with #{other}"
        case EventKind.PRODUCTION:
            text = f"produced {d['quantity']} {d['resource']}"
        case EventKind.CONSUMPTION:
            consumed = ", ".join(f"{d['consumed'][str(r)]} {r}" for r in RESOURCES)
            unmet = ", ".join(f"{d['unmet'][str(r)]} {r}" for r in RESOURCES if d["unmet"][str(r)])
            text = f"consumed {consumed}; health {d['health_before']}->{d['health_after']}"
            text += f"; unmet {unmet}" if unmet else ""
            text += " (rested)" if d.get("rested") else ""
        case EventKind.OCCUPATION_CHANGED:
            text = f"changed occupation {d['previous']} -> {d['occupation']}"
        case EventKind.ORDER_REJECTED:
            text = f"order rejected ({d['reason']}): {d['order']}"
        case _:
            text = f"{event.kind}: {d}"
    return f"{prefix} {text}"


def render_period(stats: list[DailyStats], world: World) -> str:
    """Summary of a batch of simulated days, as printed by ``advance``."""
    if not stats:
        return "No days simulated."
    first, last = stats[0], stats[-1]
    trades = sum(s.trade_count for s in stats)
    value = sum(sum(s.trade_value.values()) for s in stats)
    deaths = sum(s.deaths for s in stats)
    return "\n".join(
        [
            f"Simulated days {first.day}-{last.day}: {trades:,} trades worth {format_money(value)} credits,"
            f" {deaths} death(s).",
            f"Day {last.day}: population {last.population}, prices {_resource_line(last.prices, money=True)},"
            f" Gini {last.gini:.3f}",
            f"State digest: {world.state_digest()[:16]}",
        ]
    )


def render_timeline(world: World, every: int = 10) -> str:
    header = (
        f"{'day':>4} {'pop':>4} "
        + " ".join(f"{str(r) + ' $':>9}" for r in RESOURCES)
        + f" {'trades':>7} {'units':>6} {'value':>10} {'health':>7} {'gini':>6}"
    )
    lines = [header, "-" * len(header)]
    for s in world.stats:
        if s.day % every and s.day != world.day:
            continue
        lines.append(
            f"{s.day:>4} {s.population:>4} "
            + " ".join(f"{format_money(s.prices[r]):>9}" for r in RESOURCES)
            + f" {s.trade_count:>7} {sum(s.trade_volume.values()):>6} {format_money(sum(s.trade_value.values())):>10}"
            f" {s.mean_health:>7.1f} {s.gini:>6.3f}"
        )
    return "\n".join(lines)
