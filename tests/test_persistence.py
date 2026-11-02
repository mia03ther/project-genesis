"""SQLite save files: round trips, continuation, versioning and corruption."""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from genesis.invariants import audit_event_log
from genesis.models import SaveFormatError, SimulationConfig
from genesis.persistence import SCHEMA_VERSION, load_world, read_save_info, save_world
from genesis.simulation import Simulation
from genesis.world import World, create_world
from tests.conftest import run_world


def test_round_trip_preserves_every_detail(world_100: World, tmp_path: Path) -> None:
    path = save_world(world_100, tmp_path / "world.db")
    loaded = load_world(path)
    assert loaded.to_dict() == world_100.to_dict()
    assert loaded.state_digest() == world_100.state_digest()
    assert audit_event_log(loaded) == []


def test_round_trip_of_a_fresh_world_with_custom_config(tmp_path: Path) -> None:
    config = SimulationConfig(
        num_residents=7, initial_cash=5_000, daily_needs={"food": 2, "wood": 1, "stone": 0}
    )
    world = create_world(config, seed=11)
    loaded = load_world(save_world(world, tmp_path / "custom.db"))
    assert loaded.config == config
    assert loaded.state_digest() == world.state_digest()


def test_save_load_continue_equals_an_uninterrupted_run(world_100: World, tmp_path: Path) -> None:
    world = run_world(50)
    path = save_world(world, tmp_path / "halfway.db")
    resumed = load_world(path)
    Simulation(resumed).run(50)
    assert resumed.state_digest() == world_100.state_digest()


def test_saving_again_replaces_the_previous_snapshot(tmp_path: Path) -> None:
    path = tmp_path / "world.db"
    world = run_world(5)
    save_world(world, path)
    Simulation(world).run(5)
    save_world(world, path)
    loaded = load_world(path)
    assert loaded.day == 10 and loaded.state_digest() == world.state_digest()


def test_meta_records_format_and_versions(tmp_path: Path) -> None:
    path = save_world(create_world(seed=3), tmp_path / "w.db")
    info = read_save_info(path)
    assert info["format"] == "genesis.world"
    assert info["schema_version"] == str(SCHEMA_VERSION)
    assert (info["seed"], info["day"]) == ("3", "0")


def test_missing_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_world(tmp_path / "nope.db")


def test_not_a_database(tmp_path: Path) -> None:
    path = tmp_path / "notes.db"
    path.write_text("not a database at all, just some text" * 50)
    with pytest.raises(SaveFormatError):
        load_world(path)
    with pytest.raises(SaveFormatError):
        save_world(create_world(), path)
    assert path.read_text().startswith("not a database")  # untouched


def test_foreign_sqlite_database_is_never_overwritten(tmp_path: Path) -> None:
    path = tmp_path / "other.db"
    with sqlite3.connect(path) as conn:
        conn.execute("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT)")
        conn.execute("INSERT INTO customers (name) VALUES ('Ada')")
    conn.close()
    with pytest.raises(SaveFormatError, match="not a GENESIS save"):
        save_world(create_world(), path)
    with pytest.raises(SaveFormatError, match="not a GENESIS save"):
        load_world(path)
    with sqlite3.connect(path) as conn:
        assert conn.execute("SELECT name FROM customers").fetchall() == [("Ada",)]
    conn.close()


def _execute(path: Path, sql: str, *params: object) -> None:
    conn = sqlite3.connect(path)
    with conn:
        conn.execute(sql, params)
    conn.close()


def test_newer_schema_version_is_refused(tmp_path: Path) -> None:
    path = save_world(create_world(), tmp_path / "w.db")
    _execute(path, "UPDATE meta SET value = ? WHERE key = 'schema_version'", str(SCHEMA_VERSION + 1))
    with pytest.raises(SaveFormatError, match="schema version"):
        load_world(path)


def test_tampered_balances_fail_integrity_checks(tmp_path: Path) -> None:
    path = save_world(run_world(10), tmp_path / "w.db")
    _execute(path, "UPDATE residents SET cash = cash + 100 WHERE id = 1")
    with pytest.raises(SaveFormatError, match="currency not conserved"):
        load_world(path)
    assert load_world(path, verify=False).residents[0].cash > 0  # still inspectable


def test_database_constraints_reject_negative_holdings(tmp_path: Path) -> None:
    path = save_world(create_world(), tmp_path / "w.db")
    with pytest.raises(sqlite3.IntegrityError):
        _execute(path, "UPDATE inventories SET quantity = -1 WHERE resident_id = 1 AND resource = 'food'")
    with pytest.raises(sqlite3.IntegrityError):
        _execute(path, "UPDATE residents SET cash = -5 WHERE id = 1")


def test_documented_tables_exist(tmp_path: Path) -> None:
    path = save_world(create_world(), tmp_path / "w.db")
    conn = sqlite3.connect(path)
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    conn.close()
    assert tables == {
        "meta",
        "residents",
        "inventories",
        "skills",
        "market",
        "ledger",
        "events",
        "daily_stats",
    }
