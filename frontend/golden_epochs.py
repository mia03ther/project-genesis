"""Generate the golden epochs the browser engine must reproduce.

Runs a set of epochs through the real Python engine and writes
``tests/golden_epochs.json``: for each epoch the exact parameters, the full
epoch result (civilization scores, digests, winner) and a fixed set of
play-money bets plus their settlement. The JavaScript port in
``frontend/engine.js`` is verified against this file by
``frontend/verify_epochs.mjs``: same epoch in, same winner and same payouts
out — or the port is wrong.

Usage (from the repository root)::

    .venv/bin/python frontend/golden_epochs.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

from genesis.betting import Bet, place_bet, settle_epoch  # noqa: E402
from genesis.epoch import run_epoch  # noqa: E402

#: (seed, days) — civs, residents, tax and order cap stay at their defaults.
GOLDEN_EPOCHS: tuple[tuple[int, int], ...] = (
    (42, 60),   # default epoch, golden seed
    (7, 30),    # shortest epoch
    (123, 90),  # longest epoch
)

#: Fixed play-money bets (player, civ, amount in cents), placed on every epoch.
GOLDEN_BETS: tuple[tuple[str, int, int], ...] = (
    ("alice", 0, 1000),
    ("bob", 1, 2500),
    ("carol", 2, 500),
    ("dan", 0, 10_000),
    ("alice", 3, 750),
    ("bob", 2, 3000),
)


def main() -> int:
    goldens = []
    for seed, days in GOLDEN_EPOCHS:
        epoch = run_epoch(seed=seed, days=days)
        epoch_id = str(epoch["epoch_id"])
        valid = [civ["id"] for civ in epoch["civs"]]
        bets: list[Bet] = []
        for player, civ, amount in GOLDEN_BETS:
            bets = place_bet(
                bets, player=player, civ=civ, amount=amount, epoch_id=epoch_id, valid_civs=valid
            )
        settlement = settle_epoch(epoch, bets)
        goldens.append(
            {
                "label": f"epoch seed {seed}, {days} days, {len(valid)} civs",
                "epoch": epoch,
                "bets": [bet.to_dict() for bet in bets],
                "settlement": settlement,
            }
        )
        print(
            f"{goldens[-1]['label']}: winner {epoch['winner_name']} "
            f"(score {epoch['civs'][epoch['winner']]['score']}), "
            f"digest {epoch['digest'][:16]}, settlement {settlement['outcome']}, "
            f"pool {settlement['pool']}"
        )
    out = REPO_ROOT / "tests" / "golden_epochs.json"
    out.write_text(json.dumps(goldens, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out} ({out.stat().st_size / 1024:.0f} KiB, {len(goldens)} epochs)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
