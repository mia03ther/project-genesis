"""Versioned SQLite save files.

A save file holds exactly one world. :func:`save_world` writes a complete
snapshot inside a single transaction, so a save is either fully written or
not written at all. :func:`load_world` refuses files of another format or
schema version and, by default, re-checks the accounting invariants of what
it loaded. The schema is documented in ``docs/SAVE_FORMAT.md``.
"""

from __future__ import annotations

import json
import os
import sqlite3
from contextlib import closing
from pathlib import Path
from typing import Any

from genesis import __version__
from genesis.invariants import check_invariants
from genesis.models import (
    OCCUPATIONS,
    RESOURCES,
    DailyStats,
    Event,
    EventKind,
    Ledger,
    MarketQuote,
    Occupation,
    Resident,
    SaveFormatError,
    SimulationConfig,
)
from genesis.world import World

SAVE_FORMAT = "genesis.world"
SCHEMA_VERSION = 1

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS residents (
    id                     INTEGER PRIMARY KEY,
    name                   TEXT    NOT NULL,
    occupation             TEXT    NOT NULL,
    policy                 TEXT    NOT NULL,
    cash                   INTEGER NOT NULL CHECK (cash >= 0),
    health                 INTEGER NOT NULL CHECK (health BETWEEN 0 AND 100),
    alive                  INTEGER NOT NULL CHECK (alive IN (0, 1)),
    last_occupation_change INTEGER,
    died_on                INTEGER
);
CREATE TABLE IF NOT EXISTS inventories (
    resident_id INTEGER NOT NULL REFERENCES residents (id),
    resource    TEXT    NOT NULL,
    quantity    INTEGER NOT NULL CHECK (quantity >= 0),
    PRIMARY KEY (resident_id, resource)
);
CREATE TABLE IF NOT EXISTS skills (
    resident_id INTEGER NOT NULL REFERENCES residents (id),
    occupation  TEXT    NOT NULL,
    skill_pct   INTEGER NOT NULL CHECK (skill_pct > 0),
    PRIMARY KEY (resident_id, occupation)
);
CREATE TABLE IF NOT EXISTS market (
    resource TEXT    PRIMARY KEY,
    price    INTEGER NOT NULL CHECK (price > 0),
    demand   INTEGER NOT NULL CHECK (demand >= 0),
    supply   INTEGER NOT NULL CHECK (supply >= 0),
    volume   INTEGER NOT NULL CHECK (volume >= 0)
);
CREATE TABLE IF NOT EXISTS ledger (
    resource TEXT    PRIMARY KEY,
    initial  INTEGER NOT NULL CHECK (initial >= 0),
    produced INTEGER NOT NULL CHECK (produced >= 0),
    consumed INTEGER NOT NULL CHECK (consumed >= 0)
);
CREATE TABLE IF NOT EXISTS events (
    seq             INTEGER PRIMARY KEY,
    day             INTEGER NOT NULL,
    kind            TEXT    NOT NULL,
    resident_id     INTEGER,
    counterparty_id INTEGER,
    data            TEXT    NOT NULL
);
CREATE INDEX IF NOT EXISTS events_by_day ON events (day);
CREATE INDEX IF NOT EXISTS events_by_resident ON events (resident_id);
CREATE INDEX IF NOT EXISTS events_by_kind ON events (kind);
CREATE TABLE IF NOT EXISTS daily_stats (
    day  INTEGER PRIMARY KEY,
    data TEXT    NOT NULL
);
"""

#: Children before parents, so foreign keys stay satisfied while clearing.
_TABLES = ("inventories", "skills", "residents", "market", "ledger", "events", "daily_stats", "meta")


def _json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def read_save_info(path: str | os.PathLike[str]) -> dict[str, str]:
    """Return the ``meta`` table of a save file after checking its format and version."""
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"no saved world at {source}")
    try:
        with closing(sqlite3.connect(source)) as conn:
            return _read_meta(conn, source)
    except sqlite3.DatabaseError as error:
        raise SaveFormatError(f"{source} is not a GENESIS save file: {error}") from error


def _read_meta(conn: sqlite3.Connection, source: Path) -> dict[str, str]:
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
    if "meta" not in tables:
        raise SaveFormatError(f"{source} is not a GENESIS save file (no meta table)")
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    if meta.get("format") != SAVE_FORMAT:
        raise SaveFormatError(f"{source} is not a GENESIS save file (format {meta.get('format')!r})")
    version = meta.get("schema_version", "")
    if version != str(SCHEMA_VERSION):
        raise SaveFormatError(
            f"{source} uses save schema version {version!r}; this build reads version {SCHEMA_VERSION}"
        )
    return meta


def save_world(world: World, path: str | os.PathLike[str]) -> Path:
    """Write ``world`` to ``path``, replacing any world previously saved there.

    Refuses to overwrite a file that is not a GENESIS save of the same schema
    version, so a mistyped path cannot destroy an unrelated database.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        with closing(sqlite3.connect(target)) as conn:
            tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type = 'table'")}
            if tables:
                _read_meta(conn, target)  # raises unless this is a compatible GENESIS save
            conn.execute("PRAGMA foreign_keys = ON")
            conn.executescript(SCHEMA)
            with conn:
                for table in _TABLES:
                    conn.execute(f"DELETE FROM {table}")  # table names are constants, not input
                _write(conn, world)
    except sqlite3.DatabaseError as error:
        raise SaveFormatError(f"cannot save to {target}: {error}") from error
    return target


def _write(conn: sqlite3.Connection, world: World) -> None:
    meta = {
        "format": SAVE_FORMAT,
        "schema_version": str(SCHEMA_VERSION),
        "genesis_version": __version__,
        "seed": str(world.seed),
        "day": str(world.day),
        "money_supply": str(world.ledger.money_supply),
        "config": _json(world.config.to_dict()),
    }
    conn.executemany("INSERT INTO meta (key, value) VALUES (?, ?)", sorted(meta.items()))
    conn.executemany(
        "INSERT INTO residents (id, name, occupation, policy, cash, health, alive, last_occupation_change, died_on)"
        " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        [
            (
                r.id,
                r.name,
                str(r.occupation),
                r.policy,
                r.cash,
                r.health,
                int(r.alive),
                r.last_occupation_change,
                r.died_on,
            )
            for r in world.residents
        ],
    )
    conn.executemany(
        "INSERT INTO inventories (resident_id, resource, quantity) VALUES (?, ?, ?)",
        [(r.id, str(res), r.inventory[res]) for r in world.residents for res in RESOURCES],
    )
    conn.executemany(
        "INSERT INTO skills (resident_id, occupation, skill_pct) VALUES (?, ?, ?)",
        [(r.id, str(occ), r.skills[occ]) for r in world.residents for occ in OCCUPATIONS],
    )
    conn.executemany(
        "INSERT INTO market (resource, price, demand, supply, volume) VALUES (?, ?, ?, ?, ?)",
        [
            (str(res), q.price, q.demand, q.supply, q.volume)
            for res, q in ((r, world.market[r]) for r in RESOURCES)
        ],
    )
    ledger = world.ledger
    conn.executemany(
        "INSERT INTO ledger (resource, initial, produced, consumed) VALUES (?, ?, ?, ?)",
        [(str(r), ledger.initial[r], ledger.produced[r], ledger.consumed[r]) for r in RESOURCES],
    )
    conn.executemany(
        "INSERT INTO events (seq, day, kind, resident_id, counterparty_id, data) VALUES (?, ?, ?, ?, ?, ?)",
        [(e.seq, e.day, str(e.kind), e.resident_id, e.counterparty_id, _json(e.data)) for e in world.events],
    )
    conn.executemany(
        "INSERT INTO daily_stats (day, data) VALUES (?, ?)",
        [(s.day, _json(s.to_dict())) for s in world.stats],
    )


def load_world(path: str | os.PathLike[str], *, verify: bool = True) -> World:
    """Load the world saved at ``path``.

    With ``verify`` (the default) the state invariants are checked and a
    violation raises :class:`SaveFormatError`, so a hand-edited or corrupted
    save is never simulated further.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"no saved world at {source}")
    try:
        with closing(sqlite3.connect(source)) as conn:
            meta = _read_meta(conn, source)
            world = _read(conn, meta)
    except sqlite3.DatabaseError as error:
        raise SaveFormatError(f"{source} is not a readable GENESIS save: {error}") from error
    except (KeyError, ValueError, TypeError) as error:
        raise SaveFormatError(f"{source} is corrupt: {error!r}") from error
    if verify:
        problems = check_invariants(world)
        if problems:
            raise SaveFormatError(f"{source} failed integrity checks: {'; '.join(problems[:5])}")
    return world


def _read(conn: sqlite3.Connection, meta: dict[str, str]) -> World:
    inventories: dict[int, dict[str, int]] = {}
    for resident_id, resource, quantity in conn.execute(
        "SELECT resident_id, resource, quantity FROM inventories"
    ):
        inventories.setdefault(resident_id, {})[resource] = quantity
    skills: dict[int, dict[str, int]] = {}
    for resident_id, occupation, skill in conn.execute(
        "SELECT resident_id, occupation, skill_pct FROM skills"
    ):
        skills.setdefault(resident_id, {})[occupation] = skill

    residents = [
        Resident(
            id=rid,
            name=name,
            occupation=Occupation(occupation),
            skills={occ: skills[rid][str(occ)] for occ in OCCUPATIONS},
            cash=cash,
            inventory={res: inventories[rid][str(res)] for res in RESOURCES},
            health=health,
            alive=bool(alive),
            policy=policy,
            last_occupation_change=last_change,
            died_on=died_on,
        )
        for rid, name, occupation, policy, cash, health, alive, last_change, died_on in conn.execute(
            "SELECT id, name, occupation, policy, cash, health, alive, last_occupation_change, died_on"
            " FROM residents ORDER BY id"
        )
    ]
    market_rows = {
        row[0]: row[1:] for row in conn.execute("SELECT resource, price, demand, supply, volume FROM market")
    }
    market = {res: MarketQuote(*market_rows[str(res)]) for res in RESOURCES}
    ledger_rows = {
        row[0]: row[1:] for row in conn.execute("SELECT resource, initial, produced, consumed FROM ledger")
    }
    ledger = Ledger(
        money_supply=int(meta["money_supply"]),
        initial={res: ledger_rows[str(res)][0] for res in RESOURCES},
        produced={res: ledger_rows[str(res)][1] for res in RESOURCES},
        consumed={res: ledger_rows[str(res)][2] for res in RESOURCES},
    )
    events = [
        Event(seq, day, EventKind(kind), resident_id, counterparty_id, json.loads(data))
        for seq, day, kind, resident_id, counterparty_id, data in conn.execute(
            "SELECT seq, day, kind, resident_id, counterparty_id, data FROM events ORDER BY seq"
        )
    ]
    stats = [
        DailyStats.from_dict(json.loads(data))
        for (data,) in conn.execute("SELECT data FROM daily_stats ORDER BY day")
    ]
    return World(
        seed=int(meta["seed"]),
        config=SimulationConfig.from_dict(json.loads(meta["config"])),
        residents=residents,
        market=market,
        ledger=ledger,
        day=int(meta["day"]),
        events=events,
        stats=stats,
    )
