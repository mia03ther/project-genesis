"""Monad Testnet adapter: a separate adapter for a public test network.

This module is deliberately separate from the Anvil adapter in ``chain.py``
and is never a flag on it. The differences are fundamental:

- Accounts are real key pairs. Every transaction must be signed; there is no
  impersonation and no ``anvil_setBalance``. Funds come from the faucet, they
  cannot be set. Signing is done by Foundry's ``cast`` binary (already
  required by the harness for ``anvil``), so the runtime stays standard
  library only — no new Python dependency was added.
- History is permanent. There is no ``evm_snapshot`` / ``evm_revert`` on a
  public network, so a run can never be reset: ``MonadEnvironment.reset``
  reports that, and every Monad report records ``reset_verified: false`` with
  the reason. ``--repeat`` is refused for Monad scenarios for the same reason:
  a second run would start from different balances and a different nonce.
- The node is reached over the internet over HTTPS. The client here requires
  ``https://``; the loopback-only client in ``chain.py`` is untouched.

Private keys: a key is accepted only from the ``GENESIS_MONAD_PRIVATE_KEY``
environment variable or a ``--private-key`` CLI flag. It is never written to
a report, never printed, and error messages are redacted before they are
shown. No key — real, test or otherwise — is stored anywhere in this
repository.

Offline use: with no key and a loopback RPC URL (a local test double or an
``anvil`` node started with ``--chain-id 10143``), the adapter funds and
impersonates the scenario accounts exactly as the Anvil adapter does, and
sends the transfer unsigned. That path exists only for local testing and
never runs against a public URL.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from genesis.harness.chain import ChainError, RpcError, from_hex, require_loopback_url, to_hex
from genesis.harness.environment import AccountState, ScenarioSetupError
from genesis.harness.manifest import ScenarioManifest
from genesis.harness.runner import (
    Actor,
    ReferenceActor,
    RunResult,
    _observe,
    build_report,
    validate_submission,
)
from genesis.models import GenesisError

MONAD_TESTNET_CHAIN_ID = 10143
MONAD_TESTNET_RPC_URL = "https://testnet-rpc.monad.xyz"
MONAD_TESTNET_FAUCET_URL = "https://faucet.monad.xyz"
MONAD_TESTNET_EXPLORER_URL = "https://testnet.monadexplorer.com"
PRIVATE_KEY_ENV_VAR = "GENESIS_MONAD_PRIVATE_KEY"
LEDGER_CONTRACT_ENV_VAR = "GENESIS_MONAD_LEDGER"

RESET_NOTE = (
    "Monad Testnet history is permanent: there is no snapshot or revert, "
    "so a run cannot be reset and the next run starts from the state this run left behind."
)

_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_PRIVATE_KEY = re.compile(r"0x[0-9a-fA-F]{64}")
_DIGEST = re.compile(r"0x[0-9a-fA-F]{64}")


class MonadError(GenesisError):
    """Anything that stops a Monad Testnet run: bad key, missing tool, node error."""


class CastNotFound(MonadError):
    """The ``cast`` executable is not installed or not on PATH."""


def explorer_tx_url(tx_hash: str) -> str:
    """The public explorer page for a transaction hash."""
    return f"{MONAD_TESTNET_EXPLORER_URL}/tx/{tx_hash}"


def is_loopback_url(url: str) -> bool:
    """True when ``url`` is a loopback HTTP endpoint (local test doubles only)."""
    try:
        require_loopback_url(url)
    except ChainError:
        return False
    return True


def _redact(text: str, secret: str | None) -> str:
    """Remove a private key from a message before it is shown or stored."""
    if not secret:
        return text
    redacted = text.replace(secret, "[private key redacted]")
    if secret.startswith("0x"):
        redacted = redacted.replace(secret[2:], "[private key redacted]")
    return redacted


class PublicJsonRpcClient:
    """Minimal JSON-RPC 2.0 over HTTPS, standard library only.

    Unlike :class:`genesis.harness.chain.JsonRpcClient` this client talks to a
    public endpoint, so it requires ``https://`` and refuses anything else.
    """

    def __init__(self, url: str, *, timeout: float = 30.0) -> None:
        parts = urllib.parse.urlsplit(url)
        if parts.scheme != "https" or not parts.hostname:
            raise MonadError(f"refusing RPC endpoint {url!r}: Monad Testnet needs an https:// URL")
        self.url = url
        self.timeout = timeout
        self._next_id = 1

    def call(self, method: str, *params: object) -> Any:
        payload = json.dumps(
            {"jsonrpc": "2.0", "id": self._next_id, "method": method, "params": list(params)}
        )
        self._next_id += 1
        request = urllib.request.Request(
            self.url, data=payload.encode("utf-8"), headers={"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                body = json.loads(response.read())
        except urllib.error.HTTPError as error:
            raise ChainError(f"{method}: HTTP {error.code} from {self.url}") from error
        except (urllib.error.URLError, OSError) as error:
            reason = getattr(error, "reason", error)
            raise ChainError(f"cannot reach Monad Testnet at {self.url}: {reason}") from error
        except json.JSONDecodeError as error:
            raise ChainError(f"{method}: the node did not return JSON") from error
        if not isinstance(body, dict):
            raise ChainError(f"{method}: malformed JSON-RPC response")
        error_body = body.get("error")
        if error_body is not None:
            if isinstance(error_body, dict):
                raise RpcError(method, error_body.get("code"), error_body.get("message"))
            raise RpcError(method, None, error_body)
        return body.get("result")


class MonadChain:
    """Typed access to the few RPC methods the Monad adapter needs.

    It never calls ``evm_snapshot`` / ``evm_revert`` / ``anvil_setBalance`` /
    ``anvil_impersonateAccount`` against a public node: those methods do not
    exist there. The ``set_balance`` / ``impersonate`` helpers below are used
    only by the environment when the RPC URL is loopback (a local test double),
    and are never called for a public URL.
    """

    def __init__(self, rpc: Any) -> None:
        self.rpc = rpc

    def client_version(self) -> str:
        return str(self.rpc.call("web3_clientVersion"))

    def chain_id(self) -> int:
        return from_hex(self.rpc.call("eth_chainId"))

    def require_monad(self) -> str:
        """Return the client version, refusing any node on the wrong chain id."""
        version = self.client_version()
        chain_id = self.chain_id()
        if chain_id != MONAD_TESTNET_CHAIN_ID:
            raise MonadError(
                f"the node reports chain id {chain_id}, but Monad Testnet is {MONAD_TESTNET_CHAIN_ID}"
            )
        return version

    def balance(self, address: str) -> int:
        return from_hex(self.rpc.call("eth_getBalance", address, "latest"))

    def nonce(self, address: str) -> int:
        return from_hex(self.rpc.call("eth_getTransactionCount", address, "latest"))

    def code(self, address: str) -> str:
        return str(self.rpc.call("eth_getCode", address, "latest"))

    def send_transaction(self, transaction: dict[str, str]) -> str:
        """Send an unsigned transaction. Only a local node that impersonates
        the sender accepts this; a public node refuses it."""
        return str(self.rpc.call("eth_sendTransaction", dict(transaction)))

    def send_raw_transaction(self, raw_tx: str) -> str:
        return str(self.rpc.call("eth_sendRawTransaction", raw_tx))

    def transaction(self, tx_hash: str) -> dict[str, Any]:
        result = self.rpc.call("eth_getTransactionByHash", tx_hash)
        if not isinstance(result, dict):
            raise ChainError(f"transaction {tx_hash} not found")
        return result

    def receipt(self, tx_hash: str, *, timeout: float = 120.0, poll: float = 1.0) -> dict[str, Any]:
        """Wait for a receipt. A public network mines in its own time, so the
        default wait is two minutes, not the ten seconds Anvil needs."""
        deadline = time.monotonic() + timeout
        while True:
            result = self.rpc.call("eth_getTransactionReceipt", tx_hash)
            if isinstance(result, dict):
                return result
            if time.monotonic() >= deadline:
                raise ChainError(f"no receipt for {tx_hash} after {timeout} s")
            time.sleep(poll)

    # -- loopback-only helpers (local test doubles; never a public node) ----------

    def set_balance(self, address: str, wei: int) -> None:
        self.rpc.call("anvil_setBalance", address, to_hex(wei))

    def impersonate(self, address: str) -> None:
        self.rpc.call("anvil_impersonateAccount", address)


class Sender(Protocol):
    """Something that can send a signed transfer on the sender's behalf."""

    def address(self) -> str: ...

    def send_transfer(self, *, rpc_url: str, to: str, value_wei: int, gas_limit: int) -> str: ...


class CastSigner:
    """Signs and sends with Foundry's ``cast`` binary.

    ``cast`` is used the way the harness already uses the ``anvil`` binary: as
    an external tool, so the runtime stays standard library only. The private
    key is passed to ``cast`` as a command-line argument (that is the only
    interface ``cast`` offers for a raw key); it is never printed, never
    logged, and stripped from every error message this class raises.
    """

    def __init__(self, private_key: str, *, cast_executable: str = "cast") -> None:
        if not _PRIVATE_KEY.fullmatch(private_key or ""):
            raise MonadError(
                "the Monad private key must be '0x' followed by 64 hex digits "
                f"(from {PRIVATE_KEY_ENV_VAR} or --private-key)"
            )
        found = shutil.which(cast_executable)
        if found is None and Path(cast_executable).is_file():
            found = cast_executable
        if found is None:
            raise CastNotFound(
                f"cannot find {cast_executable!r}; install Foundry (https://getfoundry.sh) "
                "or point --cast at the cast executable"
            )
        self._private_key = private_key
        self.executable = found

    def __repr__(self) -> str:  # never include the key
        return f"CastSigner(cast={self.executable!r})"

    def _run(self, args: list[str]) -> str:
        try:
            completed = subprocess.run(
                [self.executable, *args],
                capture_output=True,
                text=True,
                timeout=120,
            )
        except subprocess.TimeoutExpired as error:
            raise MonadError(f"cast timed out after 120 s: {self._redact(str(error), self._private_key)}") from error
        except OSError as error:
            raise MonadError(f"could not run cast: {self._redact(str(error), self._private_key)}") from error
        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise MonadError(f"cast failed: {self._redact(detail, self._private_key)}")
        return completed.stdout.strip()

    def _redact(self, text: str, secret: str) -> str:
        return _redact(text, secret)

    def address(self) -> str:
        """The address of the key, derived by ``cast wallet address``."""
        result = self._run(["wallet", "address", "--private-key", self._private_key])
        address = result.strip().lower()
        if not _ADDRESS.fullmatch(address):
            raise MonadError("cast wallet address did not return an address")
        return address

    def send_transfer(self, *, rpc_url: str, to: str, value_wei: int, gas_limit: int) -> str:
        """Sign and broadcast a plain transfer; return its transaction hash."""
        output = self._run(
            [
                "send", to,
                "--value", str(value_wei),
                "--gas-limit", str(gas_limit),
                "--private-key", self._private_key,
                "--rpc-url", rpc_url,
                "--json",
            ]
        )
        try:
            data = json.loads(output)
        except json.JSONDecodeError as error:
            raise MonadError(f"cast send did not return JSON: {self._redact(output, self._private_key)}") from error
        tx_hash = data.get("transactionHash") if isinstance(data, dict) else None
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            raise MonadError(f"cast send did not return a transaction hash: {self._redact(output, self._private_key)}")
        return tx_hash

    def send_contract_call(
        self, *, rpc_url: str, contract: str, day: int, digest_hex: str, population: int, trades: int
    ) -> str:
        """Call ``recordWorldDigest(uint256,bytes32,uint32,uint64)`` on a GenesisLedger contract."""
        output = self._run(
            [
                "send", contract,
                "recordWorldDigest(uint256,bytes32,uint32,uint64)",
                str(day), digest_hex, str(population), str(trades),
                "--private-key", self._private_key,
                "--rpc-url", rpc_url,
                "--json",
            ]
        )
        try:
            data = json.loads(output)
        except json.JSONDecodeError as error:
            raise MonadError(f"cast send did not return JSON: {self._redact(output, self._private_key)}") from error
        tx_hash = data.get("transactionHash") if isinstance(data, dict) else None
        if not isinstance(tx_hash, str) or not tx_hash.startswith("0x"):
            raise MonadError(f"cast send did not return a transaction hash: {self._redact(output, self._private_key)}")
        return tx_hash


def private_key_from_env_or_flag(flag_value: str | None) -> str | None:
    """The Monad key, from a CLI flag first, then the environment. ``None`` when neither is set."""
    if flag_value:
        return flag_value
    return os.environ.get(PRIVATE_KEY_ENV_VAR) or None


class MonadEnvironment:
    """Reads the starting state on Monad Testnet and records that it cannot be restored.

    Unlike the Anvil environment this one never sets a balance, never
    impersonates an account and never snapshots. On a public network the
    balances are whatever they are; the only checks are that the chain id is
    Monad Testnet and that the sender can afford the transfer. On a loopback
    URL (a local test double) the scenario accounts are funded and
    impersonated exactly as the Anvil adapter does, so the scenario can run
    offline without a key.
    """

    def __init__(self, chain: MonadChain, manifest: ScenarioManifest, *, rpc_url: str) -> None:
        self.chain = chain
        self.manifest = manifest
        self.rpc_url = rpc_url
        self.client_version: str | None = None
        self._initialized = False

    @property
    def initialized(self) -> bool:
        return self._initialized

    def initialize(self) -> dict[str, AccountState]:
        self.client_version = self.chain.require_monad()
        if is_loopback_url(self.rpc_url):
            for account in self.manifest.accounts:
                try:
                    self.chain.set_balance(account.address, account.balance)
                    self.chain.impersonate(account.address)
                except (ChainError, RpcError):
                    # A loopback node that does not offer Anvil's methods is
                    # used as-is; the transfer will fail there if it cannot pay.
                    break
        problems = self.verify()
        if problems:
            raise ScenarioSetupError(
                "the Monad environment cannot run this scenario: " + "; ".join(problems)
            )
        self._initialized = True
        return self.state()

    def state(self) -> dict[str, AccountState]:
        return {
            account.label: AccountState(
                account.label,
                account.address,
                self.chain.balance(account.address),
                self.chain.nonce(account.address),
            )
            for account in self.manifest.accounts
        }

    def verify(self) -> list[str]:
        """Differences that would stop the run (empty when it can proceed)."""
        problems: list[str] = []
        sender = self.manifest.account(self.manifest.transaction.sender)
        balance = self.chain.balance(sender.address)
        if balance <= self.manifest.transaction.value:
            problems.append(
                f"{sender.label}: balance is {balance} wei, which does not cover the "
                f"{self.manifest.transaction.value} wei transfer plus gas; fund it from "
                f"the Monad Testnet faucet ({MONAD_TESTNET_FAUCET_URL})"
            )
        if self.chain.code(sender.address) not in ("0x", "0x0", ""):
            problems.append(f"{sender.label}: has contract code, expected a plain account")
        return problems

    def reset(self) -> bool:
        """There is no reset on a public network. Always ``False``."""
        return False

    @property
    def reset_note(self) -> str:
        return RESET_NOTE


@dataclass
class MonadRunner:
    """Runs one Monad scenario: ask the actor, send, observe, grade. Never resets."""

    manifest: ScenarioManifest
    chain: MonadChain
    rpc_url: str
    signer: Sender | None = None

    def __post_init__(self) -> None:
        self.environment = MonadEnvironment(self.chain, self.manifest, rpc_url=self.rpc_url)

    def prepare(self) -> None:
        self.environment.initialize()

    def run_once(self, actor: Actor, *, index: int = 1) -> RunResult:
        if not self.environment.initialized:
            self.prepare()
        from genesis.harness.grading import grade
        from genesis.harness.runner import TransferTask

        submission = actor.submit(TransferTask.from_manifest(self.manifest))
        described = submission.to_dict() if hasattr(submission, "to_dict") else None
        problems = validate_submission(self.manifest, submission)
        if problems:
            return RunResult(index, "rejected", actor.name, described, tuple(problems), reset_verified=False)
        assert hasattr(submission, "sender")  # established by validate_submission

        sender = self.manifest.account(submission.sender)
        recipient = self.manifest.account(submission.recipient)
        # The before-state is read before anything is sent, on both paths.
        before = self.environment.state()
        if self.signer is not None:
            signer_address = self.signer.address()
            if signer_address.lower() != sender.address.lower():
                return RunResult(
                    index,
                    "rejected",
                    actor.name,
                    described,
                    (
                        f"the key signs as {signer_address}, but the scenario's sender "
                        f"{sender.label} is {sender.address}; set the manifest's alice address "
                        "to the funded key's address before running on Monad Testnet",
                    ),
                    reset_verified=False,
                )
            try:
                tx_hash = self.signer.send_transfer(
                    rpc_url=self.rpc_url,
                    to=recipient.address,
                    value_wei=submission.value,
                    gas_limit=submission.gas_limit,
                )
            except MonadError as error:
                return RunResult(index, "rejected", actor.name, described, (str(error),), reset_verified=False)
        else:
            request = {
                "from": sender.address,
                "to": recipient.address,
                "value": to_hex(submission.value),
                "gas": to_hex(submission.gas_limit),
            }
            try:
                tx_hash = self.chain.send_transaction(request)
            except RpcError as error:
                return RunResult(
                    index, "rejected", actor.name, described,
                    (f"the chain refused it: {error}",), reset_verified=False,
                )
        receipt = self.chain.receipt(tx_hash)
        transaction = self.chain.transaction(tx_hash)
        after = self.environment.state()
        observation = _observe(
            self.manifest,
            self.environment.client_version or "",
            tx_hash,
            transaction,
            receipt,
            before,
            after,
            self.chain.chain_id(),
        )
        result = grade(self.manifest, observation)
        status = "passed" if result.passed else "failed"
        return RunResult(index, status, actor.name, described, (), observation, result, reset_verified=False)


def run_monad_scenario(
    manifest: ScenarioManifest,
    *,
    actor: Actor | None = None,
    repeat: int = 1,
    rpc_url: str | None = None,
    private_key: str | None = None,
    cast_executable: str = "cast",
) -> dict[str, Any]:
    """Run a Monad scenario once and return the JSON report.

    ``repeat`` must be 1: a public chain cannot be reset, so a second run
    would start from different balances and a different nonce. Any failure
    of the environment is reported with status ``error`` rather than raised.
    A key is only needed for a public URL; a loopback URL runs unsigned
    against a local test double.
    """
    if repeat != 1:
        raise ValueError("Monad scenarios cannot repeat: history is permanent and cannot be reset")
    actor = actor if actor is not None else ReferenceActor()
    url = rpc_url or MONAD_TESTNET_RPC_URL
    environment: dict[str, Any] = {
        "kind": "monad",
        "managed_node": False,
        "rpc_url": url,
        "reset": RESET_NOTE,
        "explorer": MONAD_TESTNET_EXPLORER_URL,
        "faucet": MONAD_TESTNET_FAUCET_URL,
    }
    runs: list[RunResult] = []
    error: str | None = None
    key: str | None = None
    try:
        key = private_key_from_env_or_flag(private_key)
        signer: Sender | None = None
        if key is not None:
            signer = CastSigner(key, cast_executable=cast_executable)
        elif not is_loopback_url(url):
            raise MonadError(
                "no Monad Testnet key: set GENESIS_MONAD_PRIVATE_KEY or pass --private-key "
                "(fund the key's address from the faucet first: "
                f"{MONAD_TESTNET_FAUCET_URL})"
            )
        if is_loopback_url(url):
            from genesis.harness.chain import JsonRpcClient

            chain = MonadChain(JsonRpcClient(url))
        else:
            chain = MonadChain(PublicJsonRpcClient(url))
        runner = MonadRunner(manifest, chain, url, signer=signer)
        runner.prepare()
        environment["client_version"] = runner.environment.client_version
        environment["chain_id"] = chain.chain_id()
        result = runner.run_once(actor, index=1)
        runs.append(result)
        if result.observation is not None and not is_loopback_url(url):
            # A loopback run has no transaction on the public chain, so
            # there is no explorer page for it; only live runs get a link.
            environment["explorer_tx_url"] = explorer_tx_url(result.observation.tx_hash)
    except GenesisError as caught:
        # Belt and braces: CastSigner already redacts, but nothing that
        # reaches a report may ever contain the key.
        error = _redact(str(caught), key)
    return build_report(manifest, actor.name, environment, runs, error)


# --- `genesis monad anchor` -----------------------------------------------------------


def cmd_anchor(args: Any) -> int:
    """Anchor a GENESIS world digest on Monad Testnet via GenesisLedger.

    Prints the transaction hash and its explorer URL. The private key comes
    from ``--private-key`` or ``GENESIS_MONAD_PRIVATE_KEY`` and is never printed.
    """
    digest_hex = (args.digest or "").strip().lower()
    if not _DIGEST.fullmatch(digest_hex):
        print("error: --digest must be '0x' followed by 64 hex digits, e.g. the demo state digest", flush=True)
        return 1
    contract = (args.contract or os.environ.get(LEDGER_CONTRACT_ENV_VAR) or "").strip().lower()
    if not _ADDRESS.fullmatch(contract):
        print(
            "error: no GenesisLedger contract address: pass --contract <address> or set "
            f"{LEDGER_CONTRACT_ENV_VAR} (deploy one first: see contracts/README.md)",
            flush=True,
        )
        return 1
    if args.day < 0:
        print("error: --day must be 0 or more", flush=True)
        return 1
    if args.population < 0 or args.trades < 0:
        print("error: --population and --trades must be 0 or more", flush=True)
        return 1
    rpc_url = args.rpc_url or MONAD_TESTNET_RPC_URL
    key = private_key_from_env_or_flag(args.private_key)
    if key is None:
        print(
            "error: no Monad Testnet key: set GENESIS_MONAD_PRIVATE_KEY or pass --private-key "
            f"(fund the key's address from the faucet first: {MONAD_TESTNET_FAUCET_URL})",
            flush=True,
        )
        return 1
    try:
        signer = CastSigner(key, cast_executable=args.cast)
        tx_hash = signer.send_contract_call(
            rpc_url=rpc_url, contract=contract, day=args.day, digest_hex=digest_hex,
            population=args.population, trades=args.trades,
        )
    except GenesisError as error:
        # Never print the key, even if an error message somehow contains it.
        print(f"error: {_redact(str(error), key)}", flush=True)
        return 1
    print(
        f"Anchored day {args.day} digest {digest_hex} "
        f"(population {args.population}, trades {args.trades}) on Monad Testnet (chain {MONAD_TESTNET_CHAIN_ID})"
    )
    print(f"  contract: {contract}")
    print(f"  tx:       {tx_hash}")
    print(f"  explorer: {explorer_tx_url(tx_hash)}")
    return 0
