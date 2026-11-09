"""Generate the golden worlds the browser engine must reproduce.

Runs a set of worlds through the real Python engine and writes
``tests/golden_worlds.json``: for each world the exact config and policy,
the state digest, the trajectory, the final summary and the residents ranked
by wealth. The JavaScript port in ``frontend/engine.js`` is verified against
this file by ``frontend/verify_engine.mjs``: same config in, same digest and
same numbers out — or the port is wrong.

The set is chosen to exercise every path the port must get exactly right:
the golden seed-42 run, a long 365-day run, a small world, the tax at 5 %,
10 % and 100 %, a shut market (0 orders — the town dies), a starving market
(2 orders), and a big 40-resident world.

Usage (from the repository root)::

    .venv/bin/python frontend/golden.py
"""

from __future__ import annotations

import json
import sys
from dataclasses import replace
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from genesis.invariants import assert_invariants  # noqa: E402
from genesis.models import SimulationConfig  # noqa: E402
from genesis.reporting import play_summary  # noqa: E402
from genesis.simulation import Simulation  # noqa: E402
from genesis.world import create_world  # noqa: E402

#: (seed, days, residents, tax_rate_bps, max_orders_per_day)
GOLDEN_WORLDS: tuple[tuple[int, int, int, int, int], ...] = (
    (42, 100, 20, 0, 10),      # the golden demo world (also anchored on Monad)
    (7, 365, 20, 0, 10),       # long run
    (1, 50, 10, 0, 10),        # small world
    (99, 100, 20, 500, 10),    # 5 % redistribution tax
    (42, 100, 20, 1_000, 10),  # 10 % tax on the golden seed
    (42, 100, 20, 0, 0),       # market shut: the town dies
    (42, 100, 20, 0, 2),       # starving market: 98 trades, town dies
    (123, 30, 5, 200, 10),     # tiny world, 2 % tax
    (2026, 200, 40, 300, 7),   # big world, 3 % tax, 7 orders
    (42, 100, 20, 10_000, 10), # 100 % tax: cash equalised every day
)


def main() -> int:
    worlds = []
    for seed, days, residents, tax_bps, max_orders in GOLDEN_WORLDS:
        config = replace(
            SimulationConfig(), num_residents=residents, max_orders_per_day=max_orders
        )
        world = create_world(config, seed=seed)
        Simulation(world, tax_rate_bps=tax_bps).run(days)
        assert_invariants(world, audit=True)
        summary = play_summary(world, tax_rate_bps=tax_bps)
        summary["label"] = (
            f"seed {seed}, {days} days, {residents} residents, "
            f"tax {tax_bps} bps, {max_orders} orders/day"
        )
        worlds.append(summary)
        print(f"{summary['label']}: digest {summary['digest'][:16]}, "
              f"gini {summary['final']['wealth']['gini']}, "
              f"alive {summary['final']['population']['alive']}")
    out = REPO_ROOT / "tests" / "golden_worlds.json"
    out.write_text(json.dumps(worlds, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KiB, {len(worlds)} worlds)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
