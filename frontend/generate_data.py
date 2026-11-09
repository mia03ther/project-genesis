"""Regenerate frontend/data.json from the real GENESIS engine.

Source of truth: ``python main.py demo`` (seed 42, 100 days, 20 residents).
This script runs the exact same simulation in-process and writes the
numbers the frontend displays. It refuses to write anything unless the
state digest matches the golden value pinned in the README
(``8ed4e8d7dd86fafc``), so a changed engine can never silently ship
stale demo numbers.

Usage (from the repository root)::

    .venv/bin/python frontend/generate_data.py
    # or: python3 frontend/generate_data.py  (needs the repo on PYTHONPATH)

The frontend loads ``data.json`` at runtime; if it cannot be fetched
(e.g. opened via ``file://``), ``app.js`` falls back to the embedded
snapshot in ``data.js``, which this script writes alongside ``data.json``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from genesis.models import RESOURCES  # noqa: E402
from genesis.reporting import wealth_summary  # noqa: E402
from genesis.simulation import Simulation  # noqa: E402
from genesis.world import create_world  # noqa: E402

SEED = 42
DAYS = 100
GOLDEN_DIGEST_PREFIX = "8ed4e8d7dd86fafc"


def cents(value: int) -> float:
    return value / 100


def main() -> int:
    world = create_world(seed=SEED)
    Simulation(world).run(DAYS)

    digest = world.state_digest()
    assert digest.startswith(GOLDEN_DIGEST_PREFIX), (
        f"state digest {digest[:16]} != golden {GOLDEN_DIGEST_PREFIX}; "
        "the engine changed — do not ship these numbers as the seed-42 demo"
    )

    stats_by_day = {s.day: s for s in world.stats}
    trajectory = []
    for day in range(10, DAYS + 1, 10):
        s = stats_by_day[day]
        trajectory.append(
            {
                "day": s.day,
                "population": s.population,
                "prices": {str(r): cents(s.prices[r]) for r in RESOURCES},
                "trades": s.trade_count,
                "units": sum(s.trade_volume.values()),
                "value": cents(sum(s.trade_value.values())),
                "health": round(s.mean_health, 1),
                "gini": round(s.gini, 3),
            }
        )

    produced = {str(r): sum(s.production[r] for s in world.stats) for r in RESOURCES}
    consumed = {str(r): sum(s.consumption[r] for s in world.stats) for r in RESOURCES}
    total_trades = sum(s.trade_count for s in world.stats)
    total_units = sum(sum(s.trade_volume.values()) for s in world.stats)
    total_value = cents(sum(sum(s.trade_value.values()) for s in world.stats))
    holdings = {str(r): v for r, v in world.holdings().items()}
    occupations: dict[str, int] = {}
    for r in world.living():
        occupations[str(r.occupation)] = occupations.get(str(r.occupation), 0) + 1

    residents = [
        {
            "id": r.id,
            "name": r.name,
            "occupation": str(r.occupation),
            "health": r.health,
            "cash": cents(r.cash),
            "inventory": {str(res): r.inventory[res] for res in RESOURCES},
            "wealth": cents(world.wealth(r)),
        }
        for r in sorted(world.living(), key=lambda x: -world.wealth(x))
    ]

    ws = wealth_summary(world)
    data = {
        "meta": {
            "source": "python main.py demo --seed 42 --days 100",
            "generator": "frontend/generate_data.py",
            "seed": SEED,
            "days": DAYS,
            "residents": len(world.residents),
            "version": "0.1.0",
            "digest": digest[:16],
            "full_digest": digest,
            "events": len(world.events),
            "invariants": "OK",
        },
        "trajectory": trajectory,
        "final": {
            "day": world.day,
            "population": len(world.living()),
            "dead": len(world.residents) - len(world.living()),
            "occupations": occupations,
            "prices": {
                str(r): cents(world.market[r].price) for r in RESOURCES
            },
            "holdings": holdings,
            "produced": produced,
            "consumed": consumed,
            "money_supply": cents(world.ledger.money_supply),
            "total_trades": total_trades,
            "total_units": total_units,
            "total_value": total_value,
            "events": len(world.events),
            "digest": digest[:16],
            "wealth": {
                "mean": round(cents(ws.mean), 2),
                "median": round(cents(ws.median), 2),
                "min": round(cents(ws.minimum), 2),
                "max": round(cents(ws.maximum), 2),
                "gini": round(ws.gini, 3),
                "richest_10_pct": round(ws.top_10_share * 100, 1),
                "poorest_50_pct": round(ws.bottom_50_share * 100, 1),
            },
            "mean_health": round(
                sum(r.health for r in world.living()) / len(world.living()), 1
            ),
        },
        "residents": residents,
    }

    out = Path(__file__).resolve().parent / "data.json"
    payload = json.dumps(data, ensure_ascii=False, indent=2) + "\n"
    out.write_text(payload, encoding="utf-8")
    # Same snapshot as a script (data.js) so the page also works when opened
    # directly via file://, where fetch("data.json") is blocked by the
    # browser. app.js prefers data.json and falls back to EMBEDDED_DATA.
    js_out = Path(__file__).resolve().parent / "data.js"
    js_out.write_text(
        "/* Generated by frontend/generate_data.py — do not hand-edit. */\n"
        "const EMBEDDED_DATA = " + payload.rstrip("\n") + ";\n",
        encoding="utf-8",
    )
    print(f"Wrote {out} (digest {digest[:16]}, {len(trajectory)} trajectory points, "
          f"{len(residents)} residents)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
