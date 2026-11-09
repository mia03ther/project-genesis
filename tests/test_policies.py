"""The two policy levers the playground exposes: the redistribution tax and
market openness (orders per day).

Both are real engine rules, not UI labels: the tax is a daily phase of the
simulation and the order cap is part of the validated config, so both change
the state digest — which is exactly what makes them demonstrable. A tax of
zero must leave the golden seed-42 digest untouched.
"""

from __future__ import annotations

import json
import subprocess
import sys
from dataclasses import replace

import pytest

from genesis.cli import main as cli_main
from genesis.invariants import assert_invariants
from genesis.models import EventKind, SimulationConfig
from genesis.reporting import play_summary, wealth_summary
from genesis.simulation import Simulation
from genesis.world import create_world
from tests.conftest import run_world
from tests.test_simulation import REFERENCE_DIGEST


def run(seed: int = 42, days: int = 100, tax_rate_bps: int = 0, **config) -> object:
    world = create_world(SimulationConfig(**config), seed=seed)
    Simulation(world, tax_rate_bps=tax_rate_bps).run(days)
    return world


def test_tax_zero_leaves_the_golden_digest_untouched() -> None:
    world = run(tax_rate_bps=0)
    assert world.state_digest() == REFERENCE_DIGEST
    assert sum(1 for e in world.events if e.kind is EventKind.TAX) == 0


def test_tax_is_money_conserving_and_fully_audited() -> None:
    world = run(tax_rate_bps=1_000)
    assert_invariants(world, audit=True)
    assert world.total_cash() == world.ledger.money_supply == 20 * 10_000
    assert sum(1 for e in world.events if e.kind is EventKind.TAX) == 100 * 20


def test_tax_flattens_wealth() -> None:
    """A 10 % daily cash tax, pooled and split equally, must lower inequality."""
    plain = wealth_summary(run(tax_rate_bps=0))
    taxed = wealth_summary(run(tax_rate_bps=1_000))
    assert taxed.gini < plain.gini
    assert taxed.maximum - taxed.minimum < plain.maximum - plain.minimum


def test_tax_changes_the_digest_and_is_deterministic() -> None:
    taxed = run(tax_rate_bps=500)
    assert taxed.state_digest() != REFERENCE_DIGEST
    assert run(tax_rate_bps=500).state_digest() == taxed.state_digest()


def test_full_tax_equalises_cash_every_day() -> None:
    """At 100 % the pool is everyone's cash, so after day 1 all living
    residents hold exactly the same cash."""
    world = run(tax_rate_bps=10_000, days=1)
    cash = {r.cash for r in world.living()}
    assert len(cash) == 1
    assert cash.pop() == world.ledger.money_supply // len(world.living())


def test_tax_rejects_out_of_range_rates() -> None:
    world = create_world(seed=1)
    with pytest.raises(ValueError):
        Simulation(world, tax_rate_bps=-1)
    with pytest.raises(ValueError):
        Simulation(world, tax_rate_bps=10_001)


def test_tax_events_carry_what_the_audit_needs() -> None:
    world = run(tax_rate_bps=500, days=3)
    day_one = [e for e in world.events if e.kind is EventKind.TAX and e.day == 1]
    assert len(day_one) == 20
    assert sum(e.data["tax_paid"] for e in day_one) == sum(e.data["rebate"] for e in day_one)
    assert all(e.data["tax_paid"] >= 0 and e.data["rebate"] >= 0 for e in day_one)


def test_no_market_means_no_trades_but_the_engine_holds() -> None:
    """Shutting the market (0 orders a day) is the playground's 'break it'
    lever: nobody can buy what they need, so health collapses — but the
    books still balance and the run stays deterministic."""
    world = run(max_orders_per_day=0)
    assert sum(s.trade_count for s in world.stats) == 0
    assert_invariants(world, audit=True)
    assert run(max_orders_per_day=0).state_digest() == world.state_digest()


def test_fewer_orders_means_fewer_trades() -> None:
    """The order cap only binds below 3 — the rule-based residents never place
    more than 3 orders a day — but below it the market starves: at 2 orders a
    day the town makes 98 trades and dies, at 10 it makes 3,867 and thrives."""
    assert sum(s.trade_count for s in run(max_orders_per_day=2).stats) == 98
    assert sum(s.trade_count for s in run(max_orders_per_day=10).stats) == 3_867


def test_play_command_prints_a_summary_with_the_same_digest(capsys: pytest.CaptureFixture[str]) -> None:
    assert cli_main(["play", "--seed", "42", "--days", "100", "--tax-bps", "500"]) == 0
    printed = json.loads(capsys.readouterr().out)
    assert printed["digest"] == run(tax_rate_bps=500).state_digest()
    assert printed["policy"] == {"tax_rate_bps": 500, "max_orders_per_day": 10}
    assert printed["final"]["trades"]["trades"] == 3_934
    assert printed["invariants"] == "OK"
    assert len(printed["residents"]) == 20
    assert printed["residents"][0]["wealth"] >= printed["residents"][-1]["wealth"]


def test_play_command_rejects_bad_policy() -> None:
    assert cli_main(["play", "--tax-bps", "10001"]) == 1
    assert cli_main(["play", "--max-orders", "-1"]) == 1


def test_play_matches_the_browser_contract() -> None:
    """The JSON the CLI prints is the contract the browser engine must match:
    integer cents everywhere, floats only for health and Gini."""
    summary = play_summary(run_world(100, seed=42))
    assert summary["digest"] == REFERENCE_DIGEST
    assert summary["final"]["trades"] == {"trades": 3867, "units": 3890, "value": 1235097,
                                          "units_by_resource": {"food": 1481, "wood": 1272, "stone": 1137},
                                          "value_by_resource": {"food": 343382, "wood": 416617, "stone": 475098}}
    assert isinstance(summary["final"]["mean_health"], float)
    assert isinstance(summary["trajectory"][0]["gini"], float)
