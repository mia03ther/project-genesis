"""Verified Monad Testnet facts, read from the shared ``frontend/chain.json``.

That JSON file is the single source of truth for chain facts both the
Python side and the frontend read; this module only loads it and renders
the clearly-labelled real-testnet path. Nothing here places a real bet,
sends a transaction, or claims a payout happened: the real-testnet path
displays already-verified facts and the exact commands to run a real
anchor/verification yourself.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

CHAIN_JSON_PATH = Path(__file__).resolve().parent.parent / "frontend" / "chain.json"


def load_chain_facts() -> dict[str, Any]:
    """Load the verified chain facts from ``frontend/chain.json``."""
    try:
        return json.loads(CHAIN_JSON_PATH.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise FileNotFoundError(
            f"shared chain facts missing: {CHAIN_JSON_PATH} not found"
        ) from None


def real_testnet_text(facts: dict[str, Any] | None = None) -> str:
    """Human-readable real-testnet block: verified facts + exact commands.

    No real bet or payout is claimed here — only facts already verified
    on-chain, plus the commands that reproduce them.
    """
    facts = facts if facts is not None else load_chain_facts()
    chain = facts["chain"]
    contract = facts["contract"]
    anchor = facts["anchor"]
    transfer = facts["first_live_transfer"]
    commands = facts["real_testnet_commands"]
    lines = [
        "REAL TESTNET — Monad Testnet (NOT play money, NOT a bet)",
        f"  chain:    {chain['name']} (id {chain['id']}), RPC {chain['rpc']}",
        f"  explorer: {chain['explorer']}",
        f"  contract: GenesisLedger {contract['address']}",
        f"    deploy tx: {contract['deploy_tx']} (fee {contract['deploy_fee_mon']} MON)",
        "  verified on-chain facts:",
        f"    first live transfer: {transfer['amount_mon']} MON, "
        f"tx {transfer['tx']}, block {transfer['block']}",
        f"    anchored digest (seed {anchor['seed']}, day {anchor['day']}): {anchor['digest']}",
        f"    anchor tx: {anchor['tx']}",
        "  No real bet has been placed by this command and no real payout",
        "  has happened. To reproduce the facts yourself, run:",
        f"    {commands['read_anchor']}",
        f"    {commands['verify_tx']}",
        "  To anchor a new digest (needs a funded key, spends real testnet MON):",
        f"    {commands['anchor_digest']}",
    ]
    return "\n".join(lines)
