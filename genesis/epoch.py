"""Epochs: short deterministic multi-civilization runs with one winner.

An epoch is a fixed, short run — 30-90 sim days — of ``num_civs`` parallel
mini-worlds ("civilizations"), each with its own seed derived from the epoch
seed. Every civilization is a real :class:`~genesis.world.World` run through
the real :class:`~genesis.simulation.Simulation`; nothing is faked or
sampled. At the end of the epoch exactly one civilization wins.

Winner rule
-----------
Each civilization gets an integer survival score::

    score = alive * 1_000_000 + wealth_cents + total_health * 100

where ``alive`` is the number of living residents, ``wealth_cents`` is the
summed wealth (cash + inventory at market prices, in integer cents) of the
living, and ``total_health`` is their summed health. Population dominates
in practice: one extra survivor outweighs any wealth gap below 1,000,000
cents (10,000 credits) — far above what a 5-resident civilization can hold
in a 30-90 day epoch (the golden epochs sit near 145,000 cents). The
highest score wins.

Tiebreak: if two or more civilizations tie on score, the winner is the
tied civilization whose ``SHA-256("genesis:epoch-winner:<epoch_digest>:<civ_id>")``
is smallest (hex comparison). The tiebreak is a pure function of the epoch
digest, so anyone holding the digest can recompute the winner without
re-running the worlds.

Epoch digest
------------
``SHA-256`` of the canonical JSON (``json.dumps`` with ``sort_keys=True``
and ``separators=(",", ":")``) of the epoch parameters plus, per
civilization, its id, name, seed, world state digest and score inputs.
The payload contains only integers and strings — no floats — so the
JavaScript port in ``frontend/engine.js`` reproduces it bit-for-bit with
its ``canonicalStringify`` + ``sha256Hex``.

Seeds
-----
Civilization ``i`` runs with seed ``epoch_seed * 1000 + i``. Epoch seeds are
restricted to ``|seed| <= 10**9`` so ``seed * 1000`` stays exactly
representable as a JavaScript double (well under 2**53) and the JS port
derives the identical seeds.

Money
-----
All epoch and betting amounts are integer cents, exactly like the rest of
GENESIS. Play money is labelled ``PLAY_MONEY_NOTE`` everywhere it surfaces:
"演示积分 · 不是真钱" (demo points, not real money).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import replace
from typing import Any

from genesis.models import SimulationConfig, is_int
from genesis.reporting import trade_totals
from genesis.simulation import Simulation
from genesis.world import create_world

#: Civilization names, in id order. ``num_civs`` must be within this list.
CIV_NAMES: tuple[str, ...] = ("Aurora", "Boreas", "Cinder", "Dune")

EPOCH_MIN_DAYS = 30
EPOCH_MAX_DAYS = 90
EPOCH_MIN_CIVS = 2
EPOCH_MAX_CIVS = len(CIV_NAMES)
EPOCH_DEFAULT_DAYS = 60
EPOCH_DEFAULT_CIVS = 4
EPOCH_DEFAULT_RESIDENTS_PER_CIV = 5
EPOCH_MAX_SEED = 10**9

#: One survivor is worth this much score; wealth and health can never bridge it.
_SCORE_PER_SURVIVOR = 1_000_000
#: One point of summed health is worth this much score (max 100 per resident).
_SCORE_PER_HEALTH = 100

PLAY_MONEY_CURRENCY = "play_credits"
#: Shown wherever play money appears. Demo points, not real money.
PLAY_MONEY_NOTE = "演示积分 · 不是真钱"


def civ_seed(epoch_seed: int, civ_index: int) -> int:
    """The world seed for civilization ``civ_index`` of an epoch."""
    return epoch_seed * 1000 + civ_index


def epoch_id_for(
    seed: int,
    days: int,
    num_civs: int,
    residents_per_civ: int,
    tax_rate_bps: int,
    max_orders_per_day: int,
) -> str:
    """The epoch id. It names every input that can change the outcome."""
    return f"epoch:{seed}:{days}:{num_civs}:{residents_per_civ}:{tax_rate_bps}:{max_orders_per_day}"


def survival_score(alive: int, wealth_cents: int, total_health: int) -> int:
    """Integer survival score: population first, then wealth, then health."""
    return alive * _SCORE_PER_SURVIVOR + wealth_cents + total_health * _SCORE_PER_HEALTH


def _winner_tiebreak_hash(epoch_digest: str, civ_id: int) -> str:
    return hashlib.sha256(f"genesis:epoch-winner:{epoch_digest}:{civ_id}".encode("utf-8")).hexdigest()


def derive_winner(scores: list[tuple[int, int]], epoch_digest: str) -> int:
    """Return the winning civilization id from ``[(civ_id, score), ...]``.

    Pure function of the scores and the epoch digest: highest score wins,
    ties broken by the smallest ``genesis:epoch-winner`` hash (see the
    module docstring). Raises ``ValueError`` on bad input.
    """
    if not isinstance(epoch_digest, str) or len(epoch_digest) != 64:
        raise ValueError(f"epoch_digest must be a 64-hex string, got {epoch_digest!r}")
    try:
        int(epoch_digest, 16)
    except ValueError:
        raise ValueError(f"epoch_digest must be a 64-hex string, got {epoch_digest!r}") from None
    if not scores:
        raise ValueError("scores must not be empty")
    civ_ids = [civ_id for civ_id, _ in scores]
    if len(set(civ_ids)) != len(civ_ids):
        raise ValueError(f"duplicate civilization ids in scores: {civ_ids!r}")
    for civ_id, score in scores:
        if not is_int(civ_id) or not is_int(score):
            raise ValueError(f"scores must be (int, int) pairs, got {(civ_id, score)!r}")
    best = max(score for _, score in scores)
    tied = [civ_id for civ_id, score in scores if score == best]
    if len(tied) == 1:
        return tied[0]
    return min(tied, key=lambda civ_id: _winner_tiebreak_hash(epoch_digest, civ_id))


def _validate_epoch_params(
    seed: int,
    days: int,
    num_civs: int,
    residents_per_civ: int,
    tax_rate_bps: int,
    max_orders_per_day: int,
) -> None:
    if not is_int(seed) or abs(seed) > EPOCH_MAX_SEED:
        raise ValueError(f"seed must be an integer with |seed| <= {EPOCH_MAX_SEED}, got {seed!r}")
    if not is_int(days) or not EPOCH_MIN_DAYS <= days <= EPOCH_MAX_DAYS:
        raise ValueError(f"days must be {EPOCH_MIN_DAYS}..{EPOCH_MAX_DAYS}, got {days!r}")
    if not is_int(num_civs) or not EPOCH_MIN_CIVS <= num_civs <= EPOCH_MAX_CIVS:
        raise ValueError(f"num_civs must be {EPOCH_MIN_CIVS}..{EPOCH_MAX_CIVS}, got {num_civs!r}")
    if not is_int(residents_per_civ) or not 1 <= residents_per_civ <= 20:
        raise ValueError(f"residents_per_civ must be 1..20, got {residents_per_civ!r}")
    if not is_int(tax_rate_bps) or not 0 <= tax_rate_bps <= 10_000:
        raise ValueError(f"tax_rate_bps must be 0..10000, got {tax_rate_bps!r}")
    if not is_int(max_orders_per_day) or not 0 <= max_orders_per_day <= 10:
        raise ValueError(f"max_orders_per_day must be 0..10, got {max_orders_per_day!r}")


def _epoch_digest(payload: dict[str, Any]) -> str:
    """SHA-256 of the canonical JSON of the epoch payload (no floats in it)."""
    text = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def run_epoch(
    seed: int = 42,
    days: int = EPOCH_DEFAULT_DAYS,
    num_civs: int = EPOCH_DEFAULT_CIVS,
    residents_per_civ: int = EPOCH_DEFAULT_RESIDENTS_PER_CIV,
    tax_rate_bps: int = 0,
    max_orders_per_day: int = 10,
) -> dict[str, Any]:
    """Run one epoch and return its JSON-ready result (see module docstring).

    The result carries ``epoch_id``, the per-civilization ``civs`` list
    (id, name, seed, world ``digest``, ``alive``, ``wealth``, ``health``,
    ``score``, ``trades``, ``units``, ``value``), the epoch ``digest`` and
    the ``winner`` id. Re-running with the same arguments returns an
    identical dict.
    """
    _validate_epoch_params(seed, days, num_civs, residents_per_civ, tax_rate_bps, max_orders_per_day)
    civs: list[dict[str, Any]] = []
    for civ_id in range(num_civs):
        config = replace(
            SimulationConfig(),
            num_residents=residents_per_civ,
            max_orders_per_day=max_orders_per_day,
        )
        world = create_world(config, seed=civ_seed(seed, civ_id))
        Simulation(world, tax_rate_bps=tax_rate_bps).run(days)
        living = world.living()
        totals = trade_totals(world)
        civs.append(
            {
                "id": civ_id,
                "name": CIV_NAMES[civ_id],
                "seed": civ_seed(seed, civ_id),
                "digest": world.state_digest(),
                "alive": len(living),
                "wealth": sum(world.wealth(resident) for resident in living),
                "health": sum(resident.health for resident in living),
                "score": survival_score(
                    len(living),
                    sum(world.wealth(resident) for resident in living),
                    sum(resident.health for resident in living),
                ),
                "trades": totals["trades"],
                "units": totals["units"],
                "value": totals["value"],
            }
        )
    payload = {
        "epoch_id": epoch_id_for(seed, days, num_civs, residents_per_civ, tax_rate_bps, max_orders_per_day),
        "seed": seed,
        "days": days,
        "num_civs": num_civs,
        "residents_per_civ": residents_per_civ,
        "tax_rate_bps": tax_rate_bps,
        "max_orders_per_day": max_orders_per_day,
        "civs": civs,
    }
    digest = _epoch_digest(payload)
    winner = derive_winner([(civ["id"], civ["score"]) for civ in civs], digest)
    return {
        **payload,
        "currency": PLAY_MONEY_CURRENCY,
        "play_money_note": PLAY_MONEY_NOTE,
        "digest": digest,
        "winner": winner,
        "winner_name": CIV_NAMES[winner],
    }
