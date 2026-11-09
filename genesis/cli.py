"""Command-line interface: ``python main.py <command>`` or, once installed, ``genesis <command>``.

Commands:

- ``init``       create a new world and save it
- ``advance``    simulate N more days and save
- ``status``     population, prices, holdings, transactions and wealth
- ``residents``  table of all residents
- ``inspect``    one resident in detail, with recent events
- ``report``     export a JSON report or a CSV table
- ``verify``     re-check every invariant and audit the full event log
- ``reset``      replace the saved world with a fresh day-0 world (asks first)
- ``demo``       run a fresh world for 100 days in memory and print a summary
- ``epoch``      run a short multi-civilization epoch with play-money bets
- ``scenario``   list, validate and run Web3 learning scenarios (``genesis.harness.cli``)
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable, Sequence
from dataclasses import replace
from pathlib import Path

from genesis import __version__
from genesis.betting import place_bet, settle_epoch
from genesis.chain import load_chain_facts, real_testnet_text
from genesis.epoch import CIV_NAMES, run_epoch
from genesis.harness.cli import register as register_scenario_commands
from genesis.invariants import assert_invariants, audit_event_log, check_invariants
from genesis.models import GenesisError, SimulationConfig
from genesis.persistence import load_world, read_save_info, save_world
from genesis.reporting import (
    CSV_TABLES,
    play_summary,
    render_period,
    render_resident,
    render_residents,
    render_status,
    render_timeline,
    write_report,
)
from genesis.simulation import Simulation
from genesis.world import World, create_world

DEFAULT_DB = "genesis_world.db"
DEFAULT_SEED = 42


def _confirm(prompt: str) -> bool:
    """Ask the user to type ``reset``. Anything else, or end of input, declines."""
    try:
        return input(prompt).strip().lower() == "reset"
    except EOFError:
        return False


def _new_world(seed: int, residents: int | None, base: SimulationConfig | None = None) -> World:
    config = base if base is not None else SimulationConfig()
    if residents is not None:
        config = replace(config, num_residents=residents)
    return create_world(config, seed=seed)


def cmd_init(args: argparse.Namespace) -> int:
    path = Path(args.db)
    if path.exists():
        print(f"error: {path} already exists; use 'reset' to start over", file=sys.stderr)
        return 1
    world = _new_world(args.seed, args.residents)
    save_world(world, path)
    print(f"Created a world with {len(world.residents)} residents (seed {world.seed}) at {path}.")
    print(render_status(world, str(path)))
    return 0


def cmd_advance(args: argparse.Namespace) -> int:
    if args.days < 1:
        print("error: --days must be at least 1", file=sys.stderr)
        return 1
    world = load_world(args.db)
    stats = Simulation(world).run(args.days)
    save_world(world, args.db)
    print(render_period(stats, world))
    return 0


def cmd_status(args: argparse.Namespace) -> int:
    print(render_status(load_world(args.db), args.db))
    return 0


def cmd_residents(args: argparse.Namespace) -> int:
    print(render_residents(load_world(args.db), sort_by=args.sort))
    return 0


def cmd_inspect(args: argparse.Namespace) -> int:
    world = load_world(args.db)
    try:
        print(render_resident(world, args.resident_id, recent=args.events))
    except KeyError:
        print(
            f"error: no resident with id {args.resident_id} (ids are 1-{len(world.residents)})",
            file=sys.stderr,
        )
        return 1
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    world = load_world(args.db)
    output = args.output
    if output is None:
        output = (
            f"genesis_report_day{world.day}.json"
            if args.format == "json"
            else f"genesis_{args.table}_day{world.day}.csv"
        )
    path = write_report(world, output, fmt=args.format, table=args.table)
    what = "JSON report" if args.format == "json" else f"CSV table '{args.table}'"
    print(f"Wrote {what} for day {world.day} to {path}")
    return 0


def cmd_verify(args: argparse.Namespace) -> int:
    world = load_world(args.db, verify=False)
    problems = check_invariants(world) + audit_event_log(world)
    if problems:
        print(f"FAILED: {len(problems)} problem(s) in {args.db}")
        for problem in problems:
            print(f"  - {problem}")
        return 1
    print(
        f"OK: day {world.day}, {len(world.events):,} events replayed; holdings are non-negative, "
        "money and resources are conserved, and every trade and market summary is consistent."
    )
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    path = Path(args.db)
    info = read_save_info(path)  # refuses to touch anything that is not a GENESIS save
    seed = args.seed if args.seed is not None else int(info["seed"])
    world = _new_world(seed, args.residents, SimulationConfig.from_dict(json.loads(info["config"])))
    if not args.yes:
        prompt = (
            f"This permanently replaces the world at {path} (day {info['day']}) with a new day-0 world "
            f"(seed {seed}). Type 'reset' to confirm: "
        )
        if not _confirm(prompt):
            print("Reset cancelled; nothing was changed.")
            return 1
    path.unlink()
    save_world(world, path)
    print(f"Reset {path}: new world at day 0 with {len(world.residents)} residents (seed {seed}).")
    return 0


def cmd_play(args: argparse.Namespace) -> int:
    """Run a world with the caller's own seed and policies and print a JSON summary.

    This is the command-line twin of the browser playground: the same config
    run here and in the browser must print the same digest. Policies are the
    two levers the playground exposes — the daily redistribution tax and how
    many orders each resident may place per day (0 shuts the market).
    """
    config = SimulationConfig()
    if args.residents is not None:
        config = replace(config, num_residents=args.residents)
    if args.max_orders is not None:
        config = replace(config, max_orders_per_day=args.max_orders)
    world = create_world(config, seed=args.seed)
    Simulation(world, tax_rate_bps=args.tax_bps or 0).run(args.days)
    assert_invariants(world, audit=True)
    print(json.dumps(play_summary(world, tax_rate_bps=args.tax_bps or 0), indent=2, sort_keys=True))
    return 0


def _parse_bet(spec: str, epoch_id: str, valid_civs: list[int]) -> tuple[str, int, int]:
    """Parse one ``--bet player:civ:amount`` spec (amount in play-credit cents)."""
    parts = spec.split(":")
    if len(parts) != 3:
        raise ValueError(f"--bet must be 'player:civ:amount', got {spec!r}")
    player, civ_text, amount_text = parts
    try:
        civ, amount = int(civ_text), int(amount_text)
    except ValueError:
        raise ValueError(f"--bet civ and amount must be integers, got {spec!r}") from None
    if civ not in valid_civs:
        raise ValueError(f"--bet civ must be one of {valid_civs}, got {civ}")
    return player, civ, amount


def cmd_epoch(args: argparse.Namespace) -> int:
    """Run one betting epoch (play money) and print its JSON result.

    With ``--real-testnet`` instead, print only the verified Monad Testnet
    facts and the exact commands to reproduce them — no epoch runs, no bet
    is placed, no payout is claimed.
    """
    if args.real_testnet:
        print(real_testnet_text(load_chain_facts()))
        return 0
    epoch = run_epoch(
        seed=args.seed,
        days=args.days,
        num_civs=args.civs,
        residents_per_civ=args.residents_per_civ,
        tax_rate_bps=args.tax_bps or 0,
        max_orders_per_day=args.max_orders if args.max_orders is not None else 10,
    )
    output: dict[str, object] = {"epoch": epoch}
    if args.bet:
        bets: list = []
        for spec in args.bet:
            player, civ, amount = _parse_bet(spec, epoch["epoch_id"], [c["id"] for c in epoch["civs"]])
            bets = place_bet(
                bets, player=player, civ=civ, amount=amount,
                epoch_id=str(epoch["epoch_id"]), valid_civs=[c["id"] for c in epoch["civs"]],
            )
        output["bets"] = [bet.to_dict() for bet in bets]
        output["settlement"] = settle_epoch(epoch, bets)
    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def cmd_demo(args: argparse.Namespace) -> int:
    world = _new_world(args.seed, args.residents)
    Simulation(world).run(args.days)
    assert_invariants(world, audit=True)
    print(
        f"Project GENESIS v{__version__} demo: {len(world.residents)} residents, seed {world.seed}, {args.days} days"
    )
    print()
    print(render_timeline(world, every=max(1, args.days // 10)))
    print()
    print(render_status(world))
    print()
    print("Invariants: OK (holdings non-negative, money and resources conserved, event log audit passed)")
    if args.save:
        save_world(world, args.save)
        print(f"Saved the world to {args.save}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="genesis",
        description="Project GENESIS: a deterministic, programmable civilization simulation.",
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    db = argparse.ArgumentParser(add_help=False)
    db.add_argument(
        "--db",
        default=os.environ.get("GENESIS_DB", DEFAULT_DB),
        help="world save file (default: %(default)s, or the GENESIS_DB environment variable)",
    )
    commands = parser.add_subparsers(dest="command", required=True, metavar="COMMAND")

    def add(
        name: str, handler: Callable[[argparse.Namespace], int], help_text: str, *, with_db: bool = True
    ) -> argparse.ArgumentParser:
        sub = commands.add_parser(
            name, parents=[db] if with_db else [], help=help_text, description=help_text
        )
        sub.set_defaults(handler=handler)
        return sub

    sub = add("init", cmd_init, "create a new world and save it")
    sub.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default: %(default)s)")
    sub.add_argument("--residents", type=int, default=None, help="number of residents (default: 20)")

    sub = add("advance", cmd_advance, "simulate more days and save the result")
    sub.add_argument("--days", type=int, default=1, help="days to simulate (default: %(default)s)")

    add("status", cmd_status, "show population, prices, holdings, transactions and wealth")

    sub = add("residents", cmd_residents, "list all residents")
    sub.add_argument(
        "--sort",
        default="id",
        choices=("id", "name", "wealth", "cash", "health", "occupation"),
        help="sort order",
    )

    sub = add("inspect", cmd_inspect, "show one resident in detail")
    sub.add_argument("resident_id", type=int, help="resident id (see 'residents')")
    sub.add_argument("--events", type=int, default=10, help="recent events to show (default: %(default)s)")

    sub = add("report", cmd_report, "export a JSON report or a CSV table")
    sub.add_argument(
        "--format", choices=("json", "csv"), default="json", help="report format (default: %(default)s)"
    )
    sub.add_argument(
        "--table", choices=CSV_TABLES, default="daily", help="CSV table to export (default: %(default)s)"
    )
    sub.add_argument("--output", default=None, help="output file (default: derived from format and day)")

    add("verify", cmd_verify, "re-check invariants and audit the whole event log")

    sub = add("reset", cmd_reset, "replace the saved world with a fresh day-0 world (asks for confirmation)")
    sub.add_argument(
        "--seed", type=int, default=None, help="seed for the new world (default: keep the current seed)"
    )
    sub.add_argument("--residents", type=int, default=None, help="number of residents (default: keep)")
    sub.add_argument("--yes", action="store_true", help="skip the confirmation prompt")

    sub = add("play", cmd_play, "run a world with your own seed and policies; print a JSON summary", with_db=False)
    sub.add_argument("--days", type=int, default=100, help="days to simulate (default: %(default)s)")
    sub.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default: %(default)s)")
    sub.add_argument("--residents", type=int, default=None, help="number of residents (default: 20)")
    sub.add_argument(
        "--tax-bps",
        type=int,
        default=None,
        help="daily redistribution tax in basis points, 0-10000 (default: 0 = off)",
    )
    sub.add_argument(
        "--max-orders",
        type=int,
        default=None,
        help="orders each resident may place per day, 0-10 (default: 10; 0 shuts the market)",
    )

    sub = add("epoch", cmd_epoch, "run a betting epoch (play money) and print its JSON result", with_db=False)
    sub.add_argument("--days", type=int, default=60, help="days per civilization, 30-90 (default: %(default)s)")
    sub.add_argument("--seed", type=int, default=DEFAULT_SEED, help="epoch seed (default: %(default)s)")
    sub.add_argument("--civs", type=int, default=4, help="civilizations, 2-4 (default: %(default)s)")
    sub.add_argument("--residents-per-civ", type=int, default=5, help="residents per civilization (default: %(default)s)")
    sub.add_argument("--tax-bps", type=int, default=None, help="daily redistribution tax in basis points (default: 0 = off)")
    sub.add_argument("--max-orders", type=int, default=None, help="orders each resident may place per day (default: 10)")
    sub.add_argument(
        "--bet", action="append", default=None, metavar="PLAYER:CIV:AMOUNT",
        help="place a play-money bet (amount in cents); repeatable, e.g. --bet alice:0:1000",
    )
    sub.add_argument(
        "--real-testnet", action="store_true",
        help="instead of running an epoch, show the verified Monad Testnet facts and commands",
    )

    sub = add("demo", cmd_demo, "run a fresh world in memory and print a summary", with_db=False)
    sub.add_argument("--days", type=int, default=100, help="days to simulate (default: %(default)s)")
    sub.add_argument("--seed", type=int, default=DEFAULT_SEED, help="random seed (default: %(default)s)")
    sub.add_argument("--residents", type=int, default=None, help="number of residents (default: 20)")
    sub.add_argument("--save", default=None, help="also save the resulting world to this file")

    register_scenario_commands(commands)

    # `genesis monad anchor`: put a GENESIS world digest on Monad Testnet via
    # the GenesisLedger contract (see contracts/README.md). Key handling lives
    # in genesis.harness.monad; the key is never printed or stored.
    from genesis.harness.monad import (
        MONAD_TESTNET_RPC_URL,
        cmd_anchor,
        cmd_verify as cmd_monad_verify,
    )

    monad = commands.add_parser(
        "monad",
        help="Monad Testnet: anchor a world digest on-chain, or verify a transaction",
        description="Monad Testnet commands. Anchoring needs a funded key "
        "(GENESIS_MONAD_PRIVATE_KEY or --private-key) and a deployed GenesisLedger "
        "contract address; nothing here runs against mainnet.",
    )
    monad_actions = monad.add_subparsers(dest="monad_command", required=True, metavar="ACTION")
    anchor = monad_actions.add_parser(
        "anchor",
        help="record a world digest on Monad Testnet and print the explorer link",
    )
    anchor.add_argument("--digest", required=True, help="state digest to anchor, '0x' + 64 hex digits")
    anchor.add_argument("--day", type=int, required=True, help="world day the digest belongs to")
    anchor.add_argument(
        "--population", type=int, default=0, help="residents alive that day (default: %(default)s)"
    )
    anchor.add_argument(
        "--trades", type=int, default=0, help="trades that had happened by that day (default: %(default)s)"
    )
    anchor.add_argument(
        "--contract", default=None,
        help="GenesisLedger address (or GENESIS_MONAD_LEDGER); deploy one first, see contracts/README.md",
    )
    anchor.add_argument(
        "--rpc-url", default=MONAD_TESTNET_RPC_URL,
        help="Monad Testnet RPC endpoint (default: %(default)s)",
    )
    anchor.add_argument(
        "--private-key", default=None,
        help="funded key (or GENESIS_MONAD_PRIVATE_KEY); never printed or stored",
    )
    anchor.add_argument(
        "--cast", default="cast", help="cast executable for signing (default: %(default)s, found on PATH)"
    )
    anchor.set_defaults(handler=cmd_anchor)

    # `genesis monad verify`: read-only proof of a transaction for judges —
    # no key, no signing, no spending; exits 0 only on a success receipt.
    verify = monad_actions.add_parser(
        "verify",
        help="show a human-readable proof of a Monad Testnet transaction (read-only)",
    )
    verify.add_argument("--tx", required=True, help="transaction hash, '0x' + 64 hex digits")
    verify.add_argument(
        "--rpc-url", default=MONAD_TESTNET_RPC_URL,
        help="Monad Testnet RPC endpoint (default: %(default)s)",
    )
    verify.set_defaults(handler=cmd_monad_verify)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return int(args.handler(args))
    except (GenesisError, FileNotFoundError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
