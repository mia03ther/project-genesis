"""``genesis scenario ...``: list, validate and run learning scenarios.

Registered into the main CLI by :func:`register`. Output is plain ASCII so it
renders in any Windows console.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from genesis.harness.manifest import ManifestError, ScenarioManifest, find_manifests, load_manifest
from genesis.harness.runner import (
    Actor,
    ReferenceActor,
    ScriptedActor,
    Submission,
    run_scenario,
    run_variants,
    write_report,
)
from genesis.harness.units import describe_wei, format_wei, parse_amount

DEFAULT_SCENARIO_DIR = "scenarios"


def resolve_scenario(reference: str, directory: str) -> Path:
    """A path to a manifest or scenario directory, or a scenario id inside ``directory``."""
    candidate = Path(reference)
    return candidate if candidate.exists() else Path(directory) / reference


def _load(reference: str, directory: str) -> ScenarioManifest | None:
    try:
        return load_manifest(resolve_scenario(reference, directory))
    except ManifestError as error:
        print(f"INVALID: {error.source or reference}")
        for problem in error.errors:
            print(f"  - {problem}")
        return None


def cmd_list(args: argparse.Namespace) -> int:
    paths = find_manifests(args.dir)
    if not paths:
        print(f"No scenarios found in {args.dir}")
        return 1
    for path in paths:
        try:
            manifest = load_manifest(path)
        except ManifestError as error:
            print(f"{path}: INVALID ({len(error.errors)} problem(s); run 'scenario validate' for details)")
            continue
        info = manifest.scenario
        print(
            f"{info.id:<28} v{info.version:<8} {info.difficulty:<12} {info.estimated_minutes:>3} min  {info.title}"
        )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    manifest = _load(args.scenario, args.dir)
    if manifest is None:
        return 1
    transfer = manifest.transaction
    print(f"OK: {manifest.scenario.id} v{manifest.scenario.version} - {manifest.scenario.title}")
    print(f"  source       {manifest.source}")
    print(f"  environment  {manifest.environment.kind}, chain id {manifest.environment.chain_id}")
    for account in manifest.accounts:
        print(
            f"  account      {account.label:<8} {account.address}  starts with {format_wei(account.balance)}"
        )
    print(f"  transaction  {transfer.sender} -> {transfer.recipient}: {describe_wei(transfer.value)}, "
          f"gas limit {transfer.gas_limit}")  # fmt: skip
    authorization = manifest.authorization
    if authorization is not None:
        print(f"  authorized   {authorization.reference}: {authorization.payer} -> {authorization.recipient}, "
              f"{format_wei(authorization.value)} on chain {authorization.chain_id}")  # fmt: skip
        for variant in manifest.variants:
            criteria = manifest.criteria_for(variant.id)
            payee = manifest.label_of(variant.request.pay_to)
            print(f"  variant      {variant.id:<20} expect {variant.expect:<7} pays {payee}, "
                  f"{len(criteria)} criteria, {sum(c.points for c in criteria)} points")  # fmt: skip
    else:
        print(f"  grading      {len(manifest.grading.criteria)} criteria, {manifest.grading.max_score} points, "
              f"pass at {manifest.grading.pass_threshold}")  # fmt: skip
    print(f"  digest       {manifest.digest()}")
    return 0


def _actor(args: argparse.Namespace, manifest: ScenarioManifest) -> Actor:
    if args.sender is None and args.to is None and args.value is None:
        return ReferenceActor()
    transfer = manifest.transaction
    return ScriptedActor(
        Submission(
            sender=args.sender or transfer.sender,
            recipient=args.to or transfer.recipient,
            value=parse_amount(args.value) if args.value is not None else transfer.value,
            gas_limit=transfer.gas_limit,
        )
    )


def cmd_run(args: argparse.Namespace) -> int:
    manifest = _load(args.scenario, args.dir)
    if manifest is None:
        return 1
    if args.repeat < 1:
        print("error: --repeat must be at least 1")
        return 1
    if manifest.variants:
        if args.sender is not None or args.to is not None or args.value is not None:
            print("error: --from, --to and --value apply only to version 1 scenarios")
            return 1
        report = run_variants(manifest, repeat=args.repeat, rpc_url=args.rpc_url, anvil_executable=args.anvil)
    else:
        report = run_scenario(
            manifest,
            actor=_actor(args, manifest),
            repeat=args.repeat,
            rpc_url=args.rpc_url,
            anvil_executable=args.anvil,
        )
    path = write_report(report, args.report or Path("reports") / f"{manifest.scenario.id}.json")
    print(render_variants_report(report) if "variants" in report else render_report(report))
    print(f"Report written to {path}")
    return 0 if report["status"] == "passed" else 1


def render_variants_report(report: Mapping[str, Any]) -> str:
    """Text summary of a version 2 (variants) report."""
    scenario = report["scenario"]
    lines = [f"Scenario {scenario['id']} v{scenario['version']}: {str(report['status']).upper()}"]
    environment = report["environment"]
    if environment.get("client_version"):
        lines.append(
            f"  node: {environment['client_version']} at {environment['rpc_url']} (chain {environment['chain_id']})"
        )
    if report["error"]:
        lines.append(f"  error: {report['error']}")
    for result in report["variants"]:
        decision = "accepted" if result["decision"]["accepted"] else "refused"
        lines.append(
            f"  {result['variant']} (repeat {result['repeat']}, expect {result['expect']}): "
            f"{decision} by {result['decision']['decided_by']} -> {result['status']}"
        )
        for criterion in result["grading"]["criteria"]:
            mark = "PASS" if criterion["passed"] else "FAIL"
            lines.append(f"    [{mark}] {criterion['id']} ({criterion['awarded']}/{criterion['points']})")
            if not criterion["passed"]:
                lines.append(f"           {criterion['explanation']}")
        lines.append(f"    normalized digest {result['normalized_digest'][:16]}, reset verified: {result['reset_verified']}")
    if report["summary"]["runs"] > len(report["reproducibility"]["normalized_digests"]):
        lines.append(f"  repeated runs consistent: {report['reproducibility']['consistent']}")
    return "\n".join(lines)


def render_report(report: Mapping[str, Any]) -> str:
    scenario = report["scenario"]
    lines = [f"Scenario {scenario['id']} v{scenario['version']}: {str(report['status']).upper()}"]
    environment = report["environment"]
    if environment.get("client_version"):
        lines.append(
            f"  node: {environment['client_version']} at {environment['rpc_url']} (chain {environment['chain_id']})"
        )
    if report["error"]:
        lines.append(f"  error: {report['error']}")
    for run in report["runs"]:
        lines.append(f"  run {run['run']} ({run['actor']}): {run['status']}")
        for reason in run["rejection_reasons"]:
            lines.append(f"    rejected: {reason}")
        grading = run["grading"]
        if grading:
            for criterion in grading["criteria"]:
                mark = "PASS" if criterion["passed"] else "FAIL"
                lines.append(f"    [{mark}] {criterion['id']} ({criterion['awarded']}/{criterion['points']})")
                if not criterion["passed"]:
                    lines.append(f"           expected {criterion['expected']}")
                    lines.append(f"           actual   {criterion['actual']}")
            lines.append(
                f"    score {grading['score']}/{grading['max_score']} (pass at {grading['pass_threshold']})"
            )
        if run["normalized_digest"]:
            lines.append(
                f"    normalized digest {run['normalized_digest'][:16]}, reset verified: {run['reset_verified']}"
            )
    reproducibility = report["reproducibility"]
    if len(report["runs"]) > 1:
        lines.append(f"  repeated runs consistent: {reproducibility['consistent']}")
    return "\n".join(lines)


def register(commands: Any) -> None:
    """Add the ``scenario`` command group to the main parser's subcommands."""
    scenario = commands.add_parser(
        "scenario",
        help="Web3 learning scenarios on a local Anvil chain",
        description="List, validate and run versioned learning scenarios on a local Anvil development chain.",
    )
    actions = scenario.add_subparsers(dest="scenario_command", required=True, metavar="ACTION")
    directory = argparse.ArgumentParser(add_help=False)
    directory.add_argument(
        "--dir", default=DEFAULT_SCENARIO_DIR, help="scenario directory (default: %(default)s)"
    )

    listing = actions.add_parser("list", parents=[directory], help="list the available scenarios")
    listing.set_defaults(handler=cmd_list)

    validate = actions.add_parser("validate", parents=[directory], help="check a scenario manifest")
    validate.add_argument("scenario", help="scenario id, scenario directory or manifest file")
    validate.set_defaults(handler=cmd_validate)

    run = actions.add_parser(
        "run", parents=[directory], help="run a scenario on a local Anvil chain and grade it"
    )
    run.add_argument("scenario", help="scenario id, scenario directory or manifest file")
    run.add_argument("--report", default=None, help="JSON report path (default: reports/<id>.json)")
    run.add_argument(
        "--repeat", type=int, default=1, help="runs from the same initial state (default: %(default)s)"
    )
    run.add_argument(
        "--anvil", default="anvil", help="anvil executable (default: %(default)s, found on PATH)"
    )
    run.add_argument("--rpc-url", default=None, help="use a running local Anvil node instead of starting one")
    run.add_argument("--from", dest="sender", default=None, help="submit from this account label instead")
    run.add_argument("--to", default=None, help="submit to this account label instead")
    run.add_argument("--value", default=None, help="submit this amount instead, e.g. '1 ether'")
    run.set_defaults(handler=cmd_run)
