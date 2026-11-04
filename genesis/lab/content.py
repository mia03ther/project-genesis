"""Mission content: briefing, evidence, hints and choices, validated against the scenario.

Mission content is teaching material; the scenario manifest it plays is the
authority on accounts, requests and grading. Loading checks that the two fit:
every variant, policy and evidence reference must exist.
"""

from __future__ import annotations

import os
import re
import tomllib
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from genesis.harness.manifest import ScenarioManifest
from genesis.lab.policies import POLICIES
from genesis.models import GenesisError, is_int

MISSION_VERSION = 1
EVIDENCE_KINDS = ("authorization", "request", "transaction", "chain", "comparison")
MISSION_FILENAME = "mission.toml"

_SLUG = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class MissionContentError(GenesisError):
    def __init__(self, errors: Sequence[str], source: str | None = None) -> None:
        self.errors = tuple(errors)
        where = f"{source}: " if source else ""
        super().__init__(f"{where}{len(self.errors)} problem(s): " + "; ".join(self.errors))


@dataclass(frozen=True, slots=True)
class EvidenceSpec:
    id: str
    title: str
    kind: str
    summary: str
    #: The variant whose request the evidence shows, for request-based kinds.
    variant: str | None
    #: Evidence that must be inspected first.
    requires: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ChoiceSpec:
    id: str
    policy: str
    label: str
    detail: str
    #: Revealed only after the replay has been graded.
    feedback: str


@dataclass(frozen=True, slots=True)
class TrustStep:
    actor: str
    trust: str
    note: str


@dataclass(frozen=True, slots=True)
class TrustBoundary:
    title: str
    summary: str
    disclaimer: str
    steps: tuple[TrustStep, ...]


@dataclass(frozen=True, slots=True)
class MissionContent:
    mission_version: int
    id: str
    scenario: str
    title: str
    tagline: str
    estimated_minutes: int
    featured_variant: str
    briefing: tuple[str, ...]
    objectives: tuple[str, ...]
    trust_boundary: TrustBoundary
    evidence: tuple[EvidenceSpec, ...]
    hints: tuple[str, ...]
    choices: tuple[ChoiceSpec, ...]

    def evidence_spec(self, evidence_id: str) -> EvidenceSpec:
        for spec in self.evidence:
            if spec.id == evidence_id:
                return spec
        raise KeyError(evidence_id)

    def choice(self, choice_id: str) -> ChoiceSpec:
        for choice in self.choices:
            if choice.id == choice_id:
                return choice
        raise KeyError(choice_id)


def load_mission(path: str | os.PathLike[str], manifest: ScenarioManifest) -> MissionContent:
    """Load ``mission.toml`` (or a directory containing it) and check it against ``manifest``."""
    target = Path(path)
    if target.is_dir():
        target = target / MISSION_FILENAME
    if not target.is_file():
        raise FileNotFoundError(f"no mission content at {target}")
    try:
        data = tomllib.loads(target.read_text(encoding="utf-8"))
    except tomllib.TOMLDecodeError as error:
        raise MissionContentError([f"cannot parse TOML: {error}"], str(target)) from error
    return parse_mission(data, manifest, source=str(target))


def _text(table: Mapping[str, Any], key: str, path: str, errors: list[str]) -> str:
    value = table.get(key)
    if not isinstance(value, str) or not value.strip():
        errors.append(f"{path}.{key}: must be a non-empty string")
        return ""
    return " ".join(value.split())


def _texts(table: Mapping[str, Any], key: str, path: str, errors: list[str], minimum: int) -> tuple[str, ...]:
    value = table.get(key)
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        errors.append(f"{path}.{key}: must be a list of non-empty strings")
        return ()
    if len(value) < minimum:
        errors.append(f"{path}.{key}: needs at least {minimum} entries")
    return tuple(" ".join(item.split()) for item in value)


def _tables(table: Mapping[str, Any], key: str, errors: list[str], minimum: int) -> list[Mapping[str, Any]]:
    value = table.get(key)
    if not isinstance(value, list) or not all(isinstance(item, Mapping) for item in value):
        errors.append(f"{key}: must be a list of tables ([[{key}]] in TOML)")
        return []
    if len(value) < minimum:
        errors.append(f"{key}: needs at least {minimum} entries")
    return value


def _unknown(table: Mapping[str, Any], path: str, allowed: set[str], errors: list[str]) -> None:
    for key in sorted(set(table) - allowed):
        errors.append(f"{path}.{key}: is not a known field")


def parse_mission(data: Mapping[str, Any], manifest: ScenarioManifest, *, source: str | None = None) -> MissionContent:
    errors: list[str] = []
    top = {"mission_version", "id", "scenario", "title", "tagline", "estimated_minutes", "featured_variant",
           "briefing", "objectives", "trust_boundary", "evidence", "hints", "choices"}  # fmt: skip
    _unknown(data, "mission", top, errors)
    version = data.get("mission_version")
    if version != MISSION_VERSION or not is_int(version):
        errors.append(f"mission_version: {version!r} is not supported; this build reads {MISSION_VERSION}")
    mission_id = _text(data, "id", "mission", errors)
    if mission_id and not _SLUG.fullmatch(mission_id):
        errors.append("mission.id: must be lower-case words joined by '-'")
    scenario = _text(data, "scenario", "mission", errors)
    if scenario and scenario != manifest.scenario.id:
        errors.append(f"mission.scenario: {scenario!r} is not the loaded scenario {manifest.scenario.id!r}")
    if not manifest.variants:
        errors.append("mission.scenario: missions need a scenario with variants (manifest version 2)")
    variant_ids = {variant.id for variant in manifest.variants}
    featured = _text(data, "featured_variant", "mission", errors)
    if featured and featured not in variant_ids:
        errors.append(f"mission.featured_variant: {featured!r} is not one of the scenario's variants")
    minutes = data.get("estimated_minutes")
    if type(minutes) is not int or not 1 <= minutes <= 600:
        errors.append("mission.estimated_minutes: must be an integer from 1 to 600")
        minutes = 1
    title = _text(data, "title", "mission", errors)
    tagline = _text(data, "tagline", "mission", errors)
    briefing = _texts(data, "briefing", "mission", errors, 1)
    objectives = _texts(data, "objectives", "mission", errors, 1)

    boundary_raw = data.get("trust_boundary")
    steps: list[TrustStep] = []
    boundary = TrustBoundary("", "", "", ())
    if not isinstance(boundary_raw, Mapping):
        errors.append("trust_boundary: must be a table")
    else:
        _unknown(boundary_raw, "trust_boundary", {"title", "summary", "disclaimer", "steps"}, errors)
        for index, step in enumerate(_tables(boundary_raw, "steps", errors, 2)):
            path = f"trust_boundary.steps[{index}]"
            _unknown(step, path, {"actor", "trust", "note"}, errors)
            steps.append(TrustStep(_text(step, "actor", path, errors), _text(step, "trust", path, errors),
                                   _text(step, "note", path, errors)))  # fmt: skip
        boundary = TrustBoundary(
            _text(boundary_raw, "title", "trust_boundary", errors),
            _text(boundary_raw, "summary", "trust_boundary", errors),
            _text(boundary_raw, "disclaimer", "trust_boundary", errors),
            tuple(steps),
        )

    evidence: list[EvidenceSpec] = []
    for index, item in enumerate(_tables(data, "evidence", errors, 1)):
        path = f"evidence[{index}]"
        _unknown(item, path, {"id", "title", "kind", "summary", "variant", "requires"}, errors)
        kind = _text(item, "kind", path, errors)
        if kind and kind not in EVIDENCE_KINDS:
            errors.append(f"{path}.kind: must be one of {', '.join(EVIDENCE_KINDS)}")
        variant = item.get("variant")
        if kind in ("request", "transaction", "comparison") and variant not in variant_ids:
            errors.append(f"{path}.variant: {kind} evidence needs one of the scenario's variants")
        requires = item.get("requires", [])
        if not isinstance(requires, list) or not all(isinstance(r, str) for r in requires):
            errors.append(f"{path}.requires: must be a list of evidence ids")
            requires = []
        evidence.append(
            EvidenceSpec(
                id=_text(item, "id", path, errors),
                title=_text(item, "title", path, errors),
                kind=kind,
                summary=_text(item, "summary", path, errors),
                variant=variant if isinstance(variant, str) else None,
                requires=tuple(requires),
            )
        )
    evidence_ids = [spec.id for spec in evidence]
    if len(set(evidence_ids)) != len(evidence_ids):
        errors.append("evidence: ids must be unique")
    for spec in evidence:
        for required in spec.requires:
            if required not in evidence_ids or required == spec.id:
                errors.append(f"evidence {spec.id!r}: requires unknown evidence {required!r}")

    hints = []
    for index, item in enumerate(_tables(data, "hints", errors, 2)):
        _unknown(item, f"hints[{index}]", {"text"}, errors)
        hints.append(_text(item, "text", f"hints[{index}]", errors))

    choices = []
    for index, item in enumerate(_tables(data, "choices", errors, 2)):
        path = f"choices[{index}]"
        _unknown(item, path, {"id", "policy", "label", "detail", "feedback"}, errors)
        policy = _text(item, "policy", path, errors)
        if policy and policy not in POLICIES:
            errors.append(f"{path}.policy: {policy!r} is not a known strategy ({', '.join(POLICIES)})")
        choices.append(
            ChoiceSpec(
                id=_text(item, "id", path, errors),
                policy=policy,
                label=_text(item, "label", path, errors),
                detail=_text(item, "detail", path, errors),
                feedback=_text(item, "feedback", path, errors),
            )
        )
    if len({choice.id for choice in choices}) != len(choices):
        errors.append("choices: ids must be unique")

    if errors:
        raise MissionContentError(errors, source)
    return MissionContent(
        mission_version=MISSION_VERSION,
        id=mission_id,
        scenario=scenario,
        title=title,
        tagline=tagline,
        estimated_minutes=int(minutes),
        featured_variant=featured,
        briefing=briefing,
        objectives=objectives,
        trust_boundary=boundary,
        evidence=tuple(evidence),
        hints=tuple(hints),
        choices=tuple(choices),
    )

