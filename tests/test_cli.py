"""The command-line interface, driven through ``main(argv)``."""

from __future__ import annotations

import csv
import json
from pathlib import Path

import pytest

from genesis import cli
from genesis.persistence import load_world


@pytest.fixture
def db(tmp_path: Path) -> str:
    return str(tmp_path / "world.db")


def run(capsys: pytest.CaptureFixture[str], *argv: str) -> tuple[int, str, str]:
    code = cli.main(list(argv))
    captured = capsys.readouterr()
    return code, captured.out, captured.err


def test_init_creates_a_world_and_refuses_to_clobber_it(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    code, out, _ = run(capsys, "init", "--db", db, "--seed", "5")
    assert code == 0 and "20 residents" in out and Path(db).is_file()
    code, _, err = run(capsys, "init", "--db", db)
    assert code == 1 and "already exists" in err


def test_advance_status_residents_inspect(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(capsys, "init", "--db", db)
    code, out, _ = run(capsys, "advance", "--db", db, "--days", "12")
    assert code == 0 and "Simulated days 1-12" in out
    assert load_world(db).day == 12

    code, out, _ = run(capsys, "status", "--db", db)
    assert code == 0
    for text in ("day 12", "Population: 20 alive", "Market prices", "Transactions", "Gini"):
        assert text in out

    code, out, _ = run(capsys, "residents", "--db", db, "--sort", "wealth")
    assert code == 0 and len(out.strip().splitlines()) == 22  # header, rule, 20 rows

    code, out, _ = run(capsys, "inspect", "4", "--db", db, "--events", "3")
    assert code == 0 and "Resident 4" in out and "last 3 of" in out

    code, _, err = run(capsys, "inspect", "99", "--db", db)
    assert code == 1 and "no resident with id 99" in err


def test_advance_rejects_zero_days(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(capsys, "init", "--db", db)
    code, _, err = run(capsys, "advance", "--db", db, "--days", "0")
    assert code == 1 and "at least 1" in err


def test_reports(db: str, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    run(capsys, "init", "--db", db)
    run(capsys, "advance", "--db", db, "--days", "5")

    report = tmp_path / "out" / "report.json"
    assert run(capsys, "report", "--db", db, "--output", str(report))[0] == 0
    data = json.loads(report.read_text(encoding="utf-8"))
    assert data["format"] == "genesis.report" and data["world"]["day"] == 5
    assert len(data["daily"]) == 5 and len(data["residents"]) == 20
    assert data["summary"]["money_supply"] == 200_000

    for table, rows in (("daily", 5), ("residents", 20)):
        path = tmp_path / f"{table}.csv"
        assert (
            run(capsys, "report", "--db", db, "--format", "csv", "--table", table, "--output", str(path))[0]
            == 0
        )
        with path.open(newline="", encoding="utf-8") as handle:
            assert len(list(csv.DictReader(handle))) == rows

    trades = tmp_path / "trades.csv"
    run(capsys, "report", "--db", db, "--format", "csv", "--table", "trades", "--output", str(trades))
    with trades.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert rows and all(int(r["value"]) == int(r["quantity"]) * int(r["price"]) for r in rows)


def test_verify(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    run(capsys, "init", "--db", db)
    run(capsys, "advance", "--db", db, "--days", "3")
    code, out, _ = run(capsys, "verify", "--db", db)
    assert code == 0 and out.startswith("OK")


def test_reset_requires_confirmation(
    db: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run(capsys, "init", "--db", db, "--seed", "8")
    run(capsys, "advance", "--db", db, "--days", "4")

    monkeypatch.setattr("builtins.input", lambda prompt: "no thanks")
    code, out, _ = run(capsys, "reset", "--db", db)
    assert code == 1 and "cancelled" in out and load_world(db).day == 4

    monkeypatch.setattr("builtins.input", lambda prompt: "reset")
    code, out, _ = run(capsys, "reset", "--db", db)
    assert code == 0 and load_world(db).day == 0 and load_world(db).seed == 8

    code, _, _ = run(capsys, "reset", "--db", db, "--yes", "--seed", "9")
    assert code == 0 and load_world(db).seed == 9


def test_reset_treats_end_of_input_as_no(
    db: str, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    run(capsys, "init", "--db", db)
    run(capsys, "advance", "--db", db, "--days", "2")

    def eof(prompt: str) -> str:
        raise EOFError

    monkeypatch.setattr("builtins.input", eof)
    assert run(capsys, "reset", "--db", db)[0] == 1
    assert load_world(db).day == 2


def test_reset_refuses_files_that_are_not_worlds(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    path = tmp_path / "precious.db"
    path.write_bytes(b"precious data")
    code, _, err = run(capsys, "reset", "--db", str(path), "--yes")
    assert code == 1 and "error" in err and path.read_bytes() == b"precious data"


def test_commands_on_a_missing_world_fail_cleanly(db: str, capsys: pytest.CaptureFixture[str]) -> None:
    for command in ("status", "advance", "residents", "verify", "reset"):
        code, _, err = run(capsys, command, "--db", db)
        assert code == 1 and "no saved world" in err


def test_demo_prints_the_required_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    saved = tmp_path / "demo.db"
    code, out, _ = run(capsys, "demo", "--days", "100", "--save", str(saved))
    assert code == 0
    for text in ("Population:", "Resources held", "Market prices", "Transactions:", "Wealth of living", "Gini",
                 "Invariants: OK"):  # fmt: skip
        assert text in out
    assert load_world(saved).day == 100


def test_db_path_from_environment(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "env.db"
    monkeypatch.setenv("GENESIS_DB", str(path))
    assert run(capsys, "init")[0] == 0
    assert path.is_file()
