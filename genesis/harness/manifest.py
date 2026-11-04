"""The versioned scenario manifest: typed schema, loader and validation.

A manifest is authored as TOML (or JSON) and parsed into immutable dataclasses.
Validation is strict and exhaustive: unknown fields are rejected so typos never
pass silently, and every problem is reported at once with its location. The
format is specified in ``docs/SCENARIO_FORMAT.md``.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import json
import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from types import MappingProxyType
from typing import Any, Literal

from genesis.harness.units import parse_amount
from genesis.models import GenesisError, is_int

#: The newest manifest format. Version 2 adds an authorization and scenario variants.
MANIFEST_VERSION = 2
SUPPORTED_MANIFEST_VERSIONS = (1, 2)
ENVIRONMENT_KINDS = ("anvil",)
DIFFICULTIES = ("beginner", "intermediate", "advanced")
RECEIPT_STATUSES = ("success", "reverted")
VARIANT_EXPECTATIONS = ("accept", "reject")
MANIFEST_FILENAMES = ("scenario.toml", "scenario.json")

SIMPLE_TRANSFER_GAS = 21_000
MAX_GAS_LIMIT = 30_000_000
#: Addresses up to this value are rejected for scenario accounts: EVM chains put
#: precompiles and system contracts in the low address range.
RESERVED_ADDRESS_LIMIT = 0x3FF

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")
_VERSION = re.compile(r"\d+\.\d+\.\d+")
_ADDRESS = re.compile(r"0x[0-9a-fA-F]{40}")
_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")


class ManifestError(GenesisError):
    """A manifest is invalid. ``errors`` lists every problem, each with its location."""

    def __init__(self, errors: Sequence[str], source: str | None = None) -> None:
        self.errors = tuple(errors)
        self.source = source
        where = f"{source}: " if source else ""
        super().__init__(f"{where}{len(self.errors)} problem(s): " + "; ".join(self.errors))


# --- the check vocabulary ------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class CheckSpec:
    """Which criterion fields a check uses. The judge in ``grading.py`` implements them."""

    summary: str
    account: Literal["no", "required", "optional"] = "no"
    expect: Literal["no", "amount", "int", "status"] = "no"
    expect_required: bool = False
    default_expect: int | str | None = None
    #: The first manifest version whose scenarios may use the check.
    since: int = 1


CHECKS: Mapping[str, CheckSpec] = MappingProxyType(
    {
        "receipt_status": CheckSpec(
            "the receipt status is 'success' (1) or 'reverted' (0)", expect="status", default_expect="success"
        ),
        "sender": CheckSpec("the transaction was sent from the expected sender"),
        "recipient": CheckSpec("the transaction was sent to the expected recipient"),
        "value": CheckSpec("the transaction carried exactly the expected value"),
        "final_balance": CheckSpec(
            "an account's balance after the run equals 'expect'",
            account="required",
            expect="amount",
            expect_required=True,
        ),
        "sender_pays_value_and_fee": CheckSpec(
            "the sender's balance fell by exactly the value plus gas used x effective gas price"
        ),
        "gas_used": CheckSpec("the receipt's gas used equals 'expect'", expect="int", expect_required=True),
        "nonce_increment": CheckSpec(
            "an account's nonce rose by 'expect' (default: the sender, by 1)",
            account="optional",
            expect="int",
            default_expect=1,
        ),
        "decision": CheckSpec("the request was accepted or rejected as the variant expects", since=2),
        "authorized_transfer": CheckSpec(
            "any executed transfer matches the authorization exactly: payer, recipient, value and chain",
            since=2,
        ),
        "balances_unchanged": CheckSpec("no scenario account's balance or nonce changed", since=2),
    }
)


# --- the schema ----------------------------------------------------------------------


@dataclass(frozen=True, slots=True)
class ScenarioInfo:
    id: str
    version: str
    title: str
    summary: str
    learning_objectives: tuple[str, ...]
    prerequisites: tuple[str, ...]
    difficulty: str
    estimated_minutes: int
    tags: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class EnvironmentSpec:
    #: Only ``"anvil"`` (a local development chain) exists in manifest version 1.
    kind: str
    chain_id: int


@dataclass(frozen=True, slots=True)
class AccountSpec:
    label: str
    #: Lower-case ``0x`` + 40 hex digits.
    address: str
    #: Starting balance in wei.
    balance: int
    description: str


@dataclass(frozen=True, slots=True)
class TransferSpec:
    """The transaction the scenario expects: account labels, value in wei."""

    sender: str
    recipient: str
    value: int
    gas_limit: int


@dataclass(frozen=True, slots=True)
class Criterion:
    id: str
    check: str
    description: str
    points: int
    #: A failed required criterion fails the run whatever the score.
    required: bool
    account: str | None = None
    expect: int | str | None = None
    #: The variants the criterion applies to; empty means every variant (manifest version 2).
    variants: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class AuthorizationSpec:
    """What the payer actually approved: the source of truth a payment request is checked against."""

    reference: str
    description: str
    #: Account labels.
    payer: str
    recipient: str
    #: Wei.
    value: int
    chain_id: int


@dataclass(frozen=True, slots=True)
class PaymentRequest:
    """An untrusted request to pay, in the shape a Web2 API might deliver it.

    It is a simplified, invented format for teaching. It is *not* an
    implementation of x402 or of any other payment protocol.
    """

    request_id: str
    #: Lower-case address; always one of the scenario's accounts.
    pay_to: str
    value: int
    chain_id: int
    memo: str


@dataclass(frozen=True, slots=True)
class VariantSpec:
    """One version of the scenario: the same chain and authorization, a different request."""

    id: str
    title: str
    description: str
    request: PaymentRequest
    #: ``"accept"`` or ``"reject"``: what a correct validator does with the request.
    expect: str


@dataclass(frozen=True, slots=True)
class GradingSpec:
    pass_threshold: int
    criteria: tuple[Criterion, ...]

    @property
    def max_score(self) -> int:
        return sum(criterion.points for criterion in self.criteria)


@dataclass(frozen=True, slots=True)
class ScenarioManifest:
    manifest_version: int
    scenario: ScenarioInfo
    environment: EnvironmentSpec
    accounts: tuple[AccountSpec, ...]
    transaction: TransferSpec
    grading: GradingSpec
    metadata: Mapping[str, Any]
    #: Present exactly when ``manifest_version >= 2``.
    authorization: AuthorizationSpec | None = None
    variants: tuple[VariantSpec, ...] = ()
    #: Where the manifest was loaded from; not part of its identity or digest.
    source: str | None = field(default=None, compare=False)

    def account(self, label: str) -> AccountSpec:
        for account in self.accounts:
            if account.label == label:
                return account
        raise KeyError(f"scenario {self.scenario.id!r} has no account {label!r}")

    def variant(self, variant_id: str) -> VariantSpec:
        for variant in self.variants:
            if variant.id == variant_id:
                return variant
        raise KeyError(f"scenario {self.scenario.id!r} has no variant {variant_id!r}")

    def criteria_for(self, variant_id: str) -> tuple[Criterion, ...]:
        """The criteria that apply to one variant, in manifest order."""
        return tuple(c for c in self.grading.criteria if not c.variants or variant_id in c.variants)

    def label_of(self, address: str | None) -> str | None:
        """The label of an address, or ``None`` if it is not a scenario account."""
        if address is None:
            return None
        for account in self.accounts:
            if account.address == address.lower():
                return account.label
        return None

    def to_dict(self) -> dict[str, Any]:
        """Canonical, JSON-ready form. Wei amounts are decimal strings.

        Version 1 manifests produce exactly the form they always did, so their
        digests are unchanged; version 2 adds its own sections.
        """
        result = self._base_dict()
        if self.manifest_version >= 2 and self.authorization is not None:
            auth = self.authorization
            result["authorization"] = {
                "reference": auth.reference,
                "description": auth.description,
                "payer": auth.payer,
                "recipient": auth.recipient,
                "value_wei": str(auth.value),
                "chain_id": auth.chain_id,
            }
            result["variants"] = [
                {
                    "id": v.id,
                    "title": v.title,
                    "description": v.description,
                    "expect": v.expect,
                    "request": {
                        "request_id": v.request.request_id,
                        "pay_to": v.request.pay_to,
                        "value_wei": str(v.request.value),
                        "chain_id": v.request.chain_id,
                        "memo": v.request.memo,
                    },
                }
                for v in self.variants
            ]
            for criterion, entry in zip(self.grading.criteria, result["grading"]["criteria"], strict=True):
                entry["variants"] = list(criterion.variants)
        return result

    def _base_dict(self) -> dict[str, Any]:
        return {
            "manifest_version": self.manifest_version,
            "scenario": {
                "id": self.scenario.id,
                "version": self.scenario.version,
                "title": self.scenario.title,
                "summary": self.scenario.summary,
                "learning_objectives": list(self.scenario.learning_objectives),
                "prerequisites": list(self.scenario.prerequisites),
                "difficulty": self.scenario.difficulty,
                "estimated_minutes": self.scenario.estimated_minutes,
                "tags": list(self.scenario.tags),
            },
            "environment": {"kind": self.environment.kind, "chain_id": self.environment.chain_id},
            "accounts": [
                {
                    "label": a.label,
                    "address": a.address,
                    "balance_wei": str(a.balance),
                    "description": a.description,
                }
                for a in self.accounts
            ],
            "transaction": {
                "from": self.transaction.sender,
                "to": self.transaction.recipient,
                "value_wei": str(self.transaction.value),
                "gas_limit": self.transaction.gas_limit,
            },
            "grading": {
                "pass_threshold": self.grading.pass_threshold,
                "max_score": self.grading.max_score,
                "criteria": [
                    {
                        "id": c.id,
                        "check": c.check,
                        "description": c.description,
                        "points": c.points,
                        "required": c.required,
                        "account": c.account,
                        "expect": str(c.expect) if CHECKS[c.check].expect == "amount" else c.expect,
                    }
                    for c in self.grading.criteria
                ],
            },
            "metadata": dict(self.metadata),
        }

    def digest(self) -> str:
        """SHA-256 of the canonical form: equal content gives an equal digest,
        whether it was written as TOML or JSON and however it was formatted."""
        payload = json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=False)
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


# --- loading --------------------------------------------------------------------------


def resolve_manifest_path(path: str | os.PathLike[str]) -> Path:
    """A manifest file, or a scenario directory containing ``scenario.toml`` / ``scenario.json``."""
    target = Path(path)
    if target.is_dir():
        for name in MANIFEST_FILENAMES:
            if (target / name).is_file():
                return target / name
    return target


def load_manifest(path: str | os.PathLike[str]) -> ScenarioManifest:
    target = resolve_manifest_path(path)
    if not target.is_file():
        raise FileNotFoundError(f"no scenario manifest at {target}")
    text = target.read_text(encoding="utf-8")
    try:
        if target.suffix == ".toml":
            data: object = tomllib.loads(text)
        elif target.suffix == ".json":
            data = json.loads(text)
        else:
            raise ManifestError([f"unsupported file type {target.suffix!r}; use .toml or .json"], str(target))
    except (tomllib.TOMLDecodeError, json.JSONDecodeError) as error:
        raise ManifestError([f"cannot parse {target.suffix[1:].upper()}: {error}"], str(target)) from error
    return parse_manifest(data, source=str(target))


def find_manifests(directory: str | os.PathLike[str]) -> list[Path]:
    """Manifests of the scenarios in ``directory`` (one sub-directory per scenario)."""
    root = Path(directory)
    found = {path for name in MANIFEST_FILENAMES for path in root.glob(f"*/{name}")}
    return sorted(found)


# --- validation -----------------------------------------------------------------------


class _Errors:
    def __init__(self) -> None:
        self.items: list[str] = []

    def add(self, path: str, message: str) -> None:
        self.items.append(f"{path}: {message}")


def _table(raw: object, path: str, errors: _Errors) -> Mapping[str, Any] | None:
    if raw is None:
        errors.add(path, "is required")
        return None
    if not isinstance(raw, Mapping):
        errors.add(path, "must be a table")
        return None
    return raw


def _fields(
    table: Mapping[str, Any], path: str, errors: _Errors, required: set[str], optional: set[str]
) -> None:
    for key in sorted(set(table) - required - optional):
        errors.add(f"{path}.{key}", "is not a known field")
    for key in sorted(required - set(table)):
        errors.add(f"{path}.{key}", "is required")


def _text(table: Mapping[str, Any], key: str, path: str, errors: _Errors,
          pattern: re.Pattern[str] | None = None) -> str | None:  # fmt: skip
    if key not in table:
        return None  # a missing required field is reported by _fields
    value = table[key]
    if not isinstance(value, str) or not value.strip():
        errors.add(f"{path}.{key}", "must be a non-empty string")
        return None
    if pattern is not None and pattern.fullmatch(value) is None:
        errors.add(f"{path}.{key}", f"{value!r} does not have the required form")
        return None
    return value.strip()


def _integer(table: Mapping[str, Any], key: str, path: str, errors: _Errors, minimum: int, maximum: int,
             default: int | None = None) -> int | None:  # fmt: skip
    if key not in table:
        return default
    value = table[key]
    if not is_int(value):
        errors.add(f"{path}.{key}", f"must be an integer, got {value!r}")
        return None
    if not minimum <= value <= maximum:
        errors.add(f"{path}.{key}", f"must be between {minimum} and {maximum}, got {value}")
        return None
    return int(value)


def _strings(table: Mapping[str, Any], key: str, path: str, errors: _Errors, *, non_empty: bool,
             pattern: re.Pattern[str] | None = None) -> tuple[str, ...]:  # fmt: skip
    value = table.get(key, [])
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        errors.add(f"{path}.{key}", "must be a list of non-empty strings")
        return ()
    if non_empty and not value:
        errors.add(f"{path}.{key}", "must not be empty")
    if pattern is not None:
        for index, item in enumerate(value):
            if pattern.fullmatch(item) is None:
                errors.add(f"{path}.{key}[{index}]", f"{item!r} must be lower-case words joined by '-'")
    return tuple(item.strip() for item in value)


def _amount(table: Mapping[str, Any], key: str, path: str, errors: _Errors) -> int | None:
    if key not in table:
        return None  # reported by _fields
    try:
        return parse_amount(table[key])
    except ValueError as error:
        errors.add(f"{path}.{key}", str(error))
        return None


def parse_manifest(data: object, *, source: str | None = None) -> ScenarioManifest:
    """Validate plain data (parsed TOML or JSON) and build the typed manifest.

    Raises :class:`ManifestError` listing every problem found.
    """
    if not isinstance(data, Mapping):
        raise ManifestError(["the manifest must be a table (TOML) or an object (JSON)"], source)
    version = data.get("manifest_version")
    if not is_int(version) or version not in SUPPORTED_MANIFEST_VERSIONS:
        supported = ", ".join(str(v) for v in SUPPORTED_MANIFEST_VERSIONS)
        raise ManifestError(
            [f"manifest_version: {version!r} is not supported; this build reads {supported}"], source
        )

    errors = _Errors()
    manifest_version = int(version)
    required = {"manifest_version", "scenario", "environment", "accounts", "transaction", "grading"}
    if manifest_version >= 2:
        required |= {"authorization", "variants"}
    _fields(data, "manifest", errors, required, {"metadata"})
    scenario = _parse_scenario(data.get("scenario"), errors)
    environment = _parse_environment(data.get("environment"), errors)
    accounts = _parse_accounts(data.get("accounts"), errors)
    labels = {account.label: account for account in accounts}
    transaction = _parse_transaction(data.get("transaction"), labels, errors)
    authorization: AuthorizationSpec | None = None
    variants: tuple[VariantSpec, ...] = ()
    if manifest_version >= 2:
        authorization = _parse_authorization(data.get("authorization"), labels, environment, errors)
        variants = _parse_variants(data.get("variants"), accounts, errors)
        _check_reference_transaction(transaction, authorization, errors)
    grading = _parse_grading(
        data.get("grading"), labels, transaction, errors, manifest_version, {v.id for v in variants}
    )
    metadata = _parse_metadata(data.get("metadata", {}), errors)
    if errors.items or scenario is None or environment is None or transaction is None or grading is None:
        raise ManifestError(errors.items or ["the manifest is incomplete"], source)
    return ScenarioManifest(
        manifest_version=manifest_version,
        scenario=scenario,
        environment=environment,
        accounts=accounts,
        transaction=transaction,
        grading=grading,
        metadata=MappingProxyType(metadata),
        authorization=authorization,
        variants=variants,
        source=source,
    )


def _parse_scenario(raw: object, errors: _Errors) -> ScenarioInfo | None:
    table = _table(raw, "scenario", errors)
    if table is None:
        return None
    required = {"id", "version", "title", "summary", "learning_objectives", "difficulty", "estimated_minutes"}
    _fields(table, "scenario", errors, required, {"prerequisites", "tags"})
    scenario_id = _text(table, "id", "scenario", errors, _SLUG)
    version = _text(table, "version", "scenario", errors, _VERSION)
    title = _text(table, "title", "scenario", errors)
    summary = _text(table, "summary", "scenario", errors)
    objectives = _strings(table, "learning_objectives", "scenario", errors, non_empty=True)
    prerequisites = _strings(table, "prerequisites", "scenario", errors, non_empty=False)
    tags = _strings(table, "tags", "scenario", errors, non_empty=False, pattern=_SLUG)
    difficulty = _text(table, "difficulty", "scenario", errors)
    if difficulty is not None and difficulty not in DIFFICULTIES:
        errors.add("scenario.difficulty", f"must be one of {', '.join(DIFFICULTIES)}")
    minutes = _integer(table, "estimated_minutes", "scenario", errors, 1, 600)
    if scenario_id is not None and len(scenario_id) > 64:
        errors.add("scenario.id", "must be at most 64 characters")
    if scenario_id is None or version is None or title is None or summary is None:
        return None
    if difficulty is None or minutes is None:
        return None
    return ScenarioInfo(
        id=scenario_id,
        version=version,
        title=title,
        summary=" ".join(summary.split()),
        learning_objectives=objectives,
        prerequisites=prerequisites,
        difficulty=difficulty,
        estimated_minutes=minutes,
        tags=tags,
    )


def _parse_environment(raw: object, errors: _Errors) -> EnvironmentSpec | None:
    table = _table(raw, "environment", errors)
    if table is None:
        return None
    _fields(table, "environment", errors, {"kind", "chain_id"}, set())
    kind = _text(table, "kind", "environment", errors)
    if kind is not None and kind not in ENVIRONMENT_KINDS:
        errors.add("environment.kind", f"{kind!r} is not supported; only 'anvil' (a local chain) is known")
        kind = None
    chain_id = _integer(table, "chain_id", "environment", errors, 1, 2**63 - 1)
    if kind is None or chain_id is None:
        return None
    return EnvironmentSpec(kind=kind, chain_id=chain_id)


def _parse_accounts(raw: object, errors: _Errors) -> tuple[AccountSpec, ...]:
    if raw is None:
        errors.add("accounts", "is required")
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, Mapping) for item in raw):
        errors.add("accounts", "must be a list of tables ([[accounts]] in TOML)")
        return ()
    if not 2 <= len(raw) <= 16:
        errors.add("accounts", f"must list 2 to 16 accounts, got {len(raw)}")
    accounts: list[AccountSpec] = []
    seen_labels: set[str] = set()
    seen_addresses: set[str] = set()
    for index, table in enumerate(raw):
        path = f"accounts[{index}]"
        _fields(table, path, errors, {"label", "address", "balance"}, {"description"})
        label = _text(table, "label", path, errors, _SLUG)
        address = _text(table, "address", path, errors, _ADDRESS)
        balance = _amount(table, "balance", path, errors)
        description = _text(table, "description", path, errors) or ""
        if label is not None:
            if label in seen_labels:
                errors.add(f"{path}.label", f"duplicate label {label!r}")
            seen_labels.add(label)
        if address is not None:
            address = address.lower()
            if int(address, 16) <= RESERVED_ADDRESS_LIMIT:
                errors.add(f"{path}.address", "is in the reserved low address range used for precompiles")
            if address in seen_addresses:
                errors.add(f"{path}.address", f"duplicate address {address}")
            seen_addresses.add(address)
        if label is not None and address is not None and balance is not None:
            accounts.append(AccountSpec(label, address, balance, description))
    return tuple(accounts)


def _parse_transaction(
    raw: object, labels: Mapping[str, AccountSpec], errors: _Errors
) -> TransferSpec | None:
    table = _table(raw, "transaction", errors)
    if table is None:
        return None
    _fields(table, "transaction", errors, {"from", "to", "value"}, {"gas_limit"})
    sender = _text(table, "from", "transaction", errors)
    recipient = _text(table, "to", "transaction", errors)
    value = _amount(table, "value", "transaction", errors)
    gas_limit = _integer(table, "gas_limit", "transaction", errors, SIMPLE_TRANSFER_GAS, MAX_GAS_LIMIT,
                         default=SIMPLE_TRANSFER_GAS)  # fmt: skip
    for key, label in (("from", sender), ("to", recipient)):
        if label is not None and label not in labels:
            errors.add(f"transaction.{key}", f"{label!r} is not one of the scenario's accounts")
    if sender is not None and sender == recipient:
        errors.add("transaction.to", "must differ from transaction.from")
    if sender is not None and sender in labels and value is not None and labels[sender].balance <= value:
        errors.add(
            "transaction.value", "the sender's starting balance must exceed the value to leave room for gas"
        )
    if sender is None or recipient is None or value is None or gas_limit is None:
        return None
    return TransferSpec(sender=sender, recipient=recipient, value=value, gas_limit=gas_limit)


def _parse_grading(raw: object, labels: Mapping[str, AccountSpec], transaction: TransferSpec | None,
                   errors: _Errors, manifest_version: int = 1,
                   variant_ids: set[str] | None = None) -> GradingSpec | None:  # fmt: skip
    table = _table(raw, "grading", errors)
    if table is None:
        return None
    # In version 2 a variant passes only when every criterion that applies to it passes,
    # so there is no threshold to configure.
    optional = {"pass_threshold"} if manifest_version == 1 else set()
    _fields(table, "grading", errors, {"criteria"}, optional)
    raw_criteria = table.get("criteria")
    if not isinstance(raw_criteria, list) or not all(isinstance(item, Mapping) for item in raw_criteria):
        errors.add("grading.criteria", "must be a list of tables ([[grading.criteria]] in TOML)")
        return None
    if not 1 <= len(raw_criteria) <= 32:
        errors.add("grading.criteria", f"must list 1 to 32 criteria, got {len(raw_criteria)}")
    criteria: list[Criterion] = []
    seen: set[str] = set()
    for index, item in enumerate(raw_criteria):
        criterion = _parse_criterion(
            item, f"grading.criteria[{index}]", labels, transaction, errors, manifest_version, variant_ids
        )
        if criterion is None:
            continue
        if criterion.id in seen:
            errors.add(f"grading.criteria[{index}].id", f"duplicate criterion id {criterion.id!r}")
        seen.add(criterion.id)
        criteria.append(criterion)
    max_score = sum(criterion.points for criterion in criteria)
    if criteria and max_score == 0:
        errors.add("grading.criteria", "must award at least one point in total")
    threshold = _integer(table, "pass_threshold", "grading", errors, 0, max(max_score, 0), default=max_score)
    if threshold is None:
        return None
    return GradingSpec(pass_threshold=threshold, criteria=tuple(criteria))


def _parse_criterion(table: Mapping[str, Any], path: str, labels: Mapping[str, AccountSpec],
                     transaction: TransferSpec | None, errors: _Errors, manifest_version: int = 1,
                     variant_ids: set[str] | None = None) -> Criterion | None:  # fmt: skip
    optional = {"points", "required", "account", "expect"}
    if manifest_version >= 2:
        optional.add("variants")
    _fields(table, path, errors, {"id", "check", "description"}, optional)
    criterion_id = _text(table, "id", path, errors, _SLUG)
    check = _text(table, "check", path, errors)
    description = _text(table, "description", path, errors)
    points = _integer(table, "points", path, errors, 0, 100, default=1)
    required = table.get("required", False)
    if not isinstance(required, bool):
        errors.add(f"{path}.required", "must be true or false")
    if check is None:
        return None
    spec = CHECKS.get(check)
    if spec is None:
        errors.add(f"{path}.check", f"unknown check {check!r}; known checks: {', '.join(CHECKS)}")
        return None
    if spec.since > manifest_version:
        errors.add(f"{path}.check", f"check {check!r} needs manifest_version {spec.since} or later")
        return None
    variants = _strings(table, "variants", path, errors, non_empty=True) if "variants" in table else ()
    for name in variants:
        if name not in (variant_ids or set()):
            errors.add(f"{path}.variants", f"{name!r} is not one of the scenario's variants")

    account: str | None = None
    if spec.account == "no":
        if "account" in table:
            errors.add(f"{path}.account", f"is not used by check {check!r}")
    elif "account" in table:
        account = _text(table, "account", path, errors)
        if account is not None and account not in labels:
            errors.add(f"{path}.account", f"{account!r} is not one of the scenario's accounts")
    elif spec.account == "required":
        errors.add(f"{path}.account", f"is required by check {check!r}")
    elif transaction is not None:
        account = transaction.sender

    expect: int | str | None = spec.default_expect
    if spec.expect == "no":
        if "expect" in table:
            errors.add(f"{path}.expect", f"is not used by check {check!r}")
    elif "expect" not in table:
        if spec.expect_required:
            errors.add(f"{path}.expect", f"is required by check {check!r}")
    elif spec.expect == "amount":
        expect = _amount(table, "expect", path, errors)
    elif spec.expect == "int":
        expect = _integer(table, "expect", path, errors, 0, 2**63 - 1)
    elif table["expect"] not in RECEIPT_STATUSES:
        errors.add(f"{path}.expect", f"must be one of {', '.join(RECEIPT_STATUSES)}")
    else:
        expect = str(table["expect"])

    if criterion_id is None or description is None or points is None or not isinstance(required, bool):
        return None
    return Criterion(criterion_id, check, description, points, required, account, expect, variants)


def _parse_authorization(raw: object, labels: Mapping[str, AccountSpec], environment: EnvironmentSpec | None,
                         errors: _Errors) -> AuthorizationSpec | None:  # fmt: skip
    table = _table(raw, "authorization", errors)
    if table is None:
        return None
    required = {"reference", "description", "payer", "recipient", "value", "chain_id"}
    _fields(table, "authorization", errors, required, set())
    reference = _text(table, "reference", "authorization", errors)
    description = _text(table, "description", "authorization", errors)
    payer = _text(table, "payer", "authorization", errors)
    recipient = _text(table, "recipient", "authorization", errors)
    value = _amount(table, "value", "authorization", errors)
    chain_id = _integer(table, "chain_id", "authorization", errors, 1, 2**63 - 1)
    for key, label in (("payer", payer), ("recipient", recipient)):
        if label is not None and label not in labels:
            errors.add(f"authorization.{key}", f"{label!r} is not one of the scenario's accounts")
    if payer is not None and payer == recipient:
        errors.add("authorization.recipient", "must differ from authorization.payer")
    if value == 0:
        errors.add("authorization.value", "must be more than zero")
    if environment is not None and chain_id is not None and chain_id != environment.chain_id:
        errors.add("authorization.chain_id", f"must equal environment.chain_id ({environment.chain_id})")
    if reference is None or description is None or payer is None or recipient is None:
        return None
    if value is None or chain_id is None:
        return None
    return AuthorizationSpec(reference, " ".join(description.split()), payer, recipient, value, chain_id)


def _parse_variants(raw: object, accounts: Sequence[AccountSpec], errors: _Errors) -> tuple[VariantSpec, ...]:
    if raw is None:
        errors.add("variants", "is required")
        return ()
    if not isinstance(raw, list) or not all(isinstance(item, Mapping) for item in raw):
        errors.add("variants", "must be a list of tables ([[variants]] in TOML)")
        return ()
    if not 1 <= len(raw) <= 8:
        errors.add("variants", f"must list 1 to 8 variants, got {len(raw)}")
    addresses = {account.address for account in accounts}
    variants: list[VariantSpec] = []
    seen: set[str] = set()
    for index, table in enumerate(raw):
        path = f"variants[{index}]"
        _fields(table, path, errors, {"id", "title", "description", "expect", "request"}, set())
        variant_id = _text(table, "id", path, errors, _SLUG)
        title = _text(table, "title", path, errors)
        description = _text(table, "description", path, errors)
        expect = _text(table, "expect", path, errors)
        if expect is not None and expect not in VARIANT_EXPECTATIONS:
            errors.add(f"{path}.expect", f"must be one of {', '.join(VARIANT_EXPECTATIONS)}")
            expect = None
        if variant_id is not None:
            if variant_id in seen:
                errors.add(f"{path}.id", f"duplicate variant id {variant_id!r}")
            seen.add(variant_id)
        request = _parse_request(table.get("request"), f"{path}.request", addresses, errors)
        if variant_id is None or title is None or description is None or expect is None or request is None:
            continue
        variants.append(VariantSpec(variant_id, title, " ".join(description.split()), request, expect))
    return tuple(variants)


def _parse_request(raw: object, path: str, addresses: set[str], errors: _Errors) -> PaymentRequest | None:
    table = _table(raw, path, errors)
    if table is None:
        return None
    _fields(table, path, errors, {"request_id", "pay_to", "value", "chain_id"}, {"memo"})
    request_id = _text(table, "request_id", path, errors)
    pay_to = _text(table, "pay_to", path, errors, _ADDRESS)
    value = _amount(table, "value", path, errors)
    chain_id = _integer(table, "chain_id", path, errors, 1, 2**63 - 1)
    memo = _text(table, "memo", path, errors) or ""
    if pay_to is not None:
        pay_to = pay_to.lower()
        if pay_to not in addresses:
            # The harness can only execute and observe transfers between scenario accounts.
            errors.add(f"{path}.pay_to", "must be the address of one of the scenario's accounts")
    if request_id is None or pay_to is None or value is None or chain_id is None:
        return None
    return PaymentRequest(request_id, pay_to, value, chain_id, memo)


def _check_reference_transaction(transaction: TransferSpec | None, authorization: AuthorizationSpec | None,
                                 errors: _Errors) -> None:  # fmt: skip
    """In version 2 the reference transaction is the authorized transfer itself."""
    if transaction is None or authorization is None:
        return
    expected = (authorization.payer, authorization.recipient, authorization.value)
    if (transaction.sender, transaction.recipient, transaction.value) != expected:
        errors.add("transaction", "must be the authorized transfer: from, to and value must equal [authorization]")


_METADATA_LISTS = {"authors", "networks"}
_METADATA_TEXT = {"license", "notes"}
_METADATA_DATES = {"created", "updated"}


def _parse_metadata(raw: object, errors: _Errors) -> dict[str, Any]:
    if not isinstance(raw, Mapping):
        errors.add("metadata", "must be a table")
        return {}
    _fields(raw, "metadata", errors, set(), _METADATA_LISTS | _METADATA_TEXT | _METADATA_DATES)
    result: dict[str, Any] = {}
    for key in sorted(set(raw) & _METADATA_LISTS):
        result[key] = list(_strings(raw, key, "metadata", errors, non_empty=False))
    for key in sorted(set(raw) & _METADATA_TEXT):
        text = _text(raw, key, "metadata", errors)
        if text is not None:
            result[key] = text
    for key in sorted(set(raw) & _METADATA_DATES):
        value = raw[key]
        if isinstance(value, dt.date) and not isinstance(value, dt.datetime):
            result[key] = value.isoformat()
        elif isinstance(value, str) and _DATE.fullmatch(value):
            result[key] = value
        else:
            errors.add(f"metadata.{key}", "must be a date such as 2026-11-02")
    return result
