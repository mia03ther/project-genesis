"""``genesis scenario`` commands, driven through ``main(argv)``."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from genesis import cli
from tests.fake_anvil import FakeAnvilServer
from tests.harness_support import SCENARIOS, raw_manifest


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str]:
    code = cli.main(list(argv))
    return code, capsys.readouterr().out


def test_list(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "scenario", "list", "--dir", str(SCENARIOS))
    assert code == 0 and "first-local-transfer" in out and "First Local Blockchain Transfer" in out


def test_validate(capsys: pytest.CaptureFixture[str]) -> None:
    code, out = run(capsys, "scenario", "validate", "first-local-transfer", "--dir", str(SCENARIOS))
    assert code == 0 and out.startswith("OK: first-local-transfer v1.0.0")
    assert "13 points, pass at 13" in out


def test_validate_lists_every_problem(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    data = raw_manifest()
    data["transaction"]["to"] = "carol"
    data["scenario"]["difficulty"] = "expert"
    data["metadata"]["created"] = "2026-11-02"
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    code, out = run(capsys, "scenario", "validate", str(path))
    assert code == 1 and out.startswith("INVALID")
    assert "transaction.to: 'carol'" in out and "scenario.difficulty" in out


def test_run_writes_a_passing_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    report_path = tmp_path / "out" / "report.json"
    with FakeAnvilServer() as server:
        code, out = run(capsys, "scenario", "run", "first-local-transfer", "--dir", str(SCENARIOS),
                        "--rpc-url", server.url, "--report", str(report_path), "--repeat", "2")  # fmt: skip
    assert code == 0
    assert "Scenario first-local-transfer v1.0.0: PASSED" in out and "[PASS] exact-value (2/2)" in out
    assert "repeated runs consistent: True" in out
    report = json.loads(report_path.read_text(encoding="utf-8"))
    assert report["status"] == "passed" and report["summary"]["runs"] == 2


def test_run_with_a_mistake_fails(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    with FakeAnvilServer() as server:
        code, out = run(capsys, "scenario", "run", "first-local-transfer", "--dir", str(SCENARIOS),
                        "--rpc-url", server.url, "--report", str(tmp_path / "r.json"), "--value", "1 ether")  # fmt: skip
    assert code == 1
    assert "FAILED" in out and "[FAIL] exact-value (0/2)" in out and "expected 1500000000000000000 wei" in out


def test_run_without_anvil_explains_what_to_install(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = run(capsys, "scenario", "run", "first-local-transfer", "--dir", str(SCENARIOS),
                    "--anvil", "genesis-no-such-anvil-binary", "--report", str(tmp_path / "r.json"))  # fmt: skip
    assert code == 1 and "ERROR" in out and "install Foundry" in out
    assert json.loads((tmp_path / "r.json").read_text(encoding="utf-8"))["status"] == "error"


def test_run_refuses_a_bad_amount(capsys: pytest.CaptureFixture[str]) -> None:
    code = cli.main(["scenario", "run", "first-local-transfer", "--dir", str(SCENARIOS), "--value", "lots"])
    assert code == 1 and "error:" in capsys.readouterr().err
