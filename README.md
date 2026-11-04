# Project GENESIS

**GENESIS / Nomi Island: a pixel adventure for Web3 learning.** Explore a dusk
woodland with original pixel characters and bottom-screen dialogue. Move with WASD,
sprint, meet residents, carry a practice parcel, and solve a local-chain payment
mission. A desktop companion and Solidity/Remix workshop are optional. It runs
without DeepSeek Harness or model API keys.
The existing deterministic civilization engine remains available below.

For Windows reviewers, install uv, a current Node.js LTS release, and Foundry/Anvil,
then run from this checkout:

```powershell
.\scripts\Setup-Genesis.ps1
.\scripts\Start-Genesis.ps1
```

The second command opens the browser game and starts a local Anvil-backed lab.
Keep the terminal open; Ctrl+C shuts down the service it owns. Use
`Start-Genesis.ps1 -WithPet` if you also want the desktop companion. Its
**委托** button opens the game at `http://127.0.0.1:8000/`.
Use **WASD / arrow keys** to move, **Shift** to sprint, **E** near a resident to
interact, **Space** to pick up/throw the practice parcel or hop, and **Esc** for
the menu. Mouse clicks on open ground also move Nomi; small screens have a
direction pad. Start with Alice's northwest studio, visit the northeast relay,
then try a validation rule at the southern payment terminal. You can explore
without accepting the mission. The practice parcel/signals are local toys;
only the backend can execute and grade a blockchain experiment.
Press **M** to open the map. Dialogue stays at the bottom; full evidence unfolds
only when requested. **E / Enter** advances story lines. Exploration position and
collectibles save locally. The workshop now starts with an interactive rule-crafting
trial before the Solidity editor. [Design references and decisions](docs/PIXEL_ART_DIRECTION.md).

The menu opens the optional workshop, where you can edit the first Solidity
exercise in embedded Remix. To use only the pet: `.\.venv\Scripts\python.exe -m genesis.pet`.
It remains interactive while the lab is offline. See the
[reviewer setup, controls and limitations](docs/COMPANION.md) and
[Remix lesson](docs/REMIX_WORKSHOP.md). If a lab was running before an update,
restart it to load the new backend/CSP. `Start-Genesis.ps1 -Port 8011` uses a separate port.
After frontend changes rebuild and refresh the page; restart for backend changes.
[Controls and implementation limits](docs/NOMI_ISLAND.md).

**Verified scope:** local Anvil; native Windows/Tk companion; official Remix iframe
loading. DSH task-event integration, Monad Testnet, native iPhone support and
automatic grading of user-written Solidity are future work. Purple collectible-style
art does not imply NFT issuance. Desktop companion counts never modify security grades.

**A deterministic, programmable civilization simulation.** v0.1 is the
foundation: a small economy of 20 autonomous residents who produce, trade and
consume food, wood and stone in a daily market. The engine is authoritative,
every run is exactly reproducible from its seed, and the books always balance.

Alongside it, the **scenario harness** (Phase 1) runs versioned Web3 learning
scenarios on a private local Anvil chain and grades them deterministically. It
starts with *First Local Blockchain Transfer*.

The core simulator and harness use Python 3.12's standard library at runtime
(SQLite included). The optional web lab uses FastAPI/Uvicorn; the game uses
React and Canvas. Development checks use pytest, HTTPX, mypy and Ruff. The
harness additionally needs Foundry's `anvil` to run scenarios on a real local chain.

## Vision

GENESIS is meant to grow into an AI-native world you can learn in and
experiment with: a sandbox where autonomous agents, including language-model
agents, live in a simulated economy; a research platform for studying those
agents; and, ultimately, a gamified learning world for Web3. Knowledge about
blockchains is fragmented and the entry barrier is high. GENESIS aims to turn it
into a world to explore, combining a wiki, a visual knowledge map, interactive
on-chain experiments and AI NPC mentors. Newcomers progress, level by level,
from understanding what a blockchain is to writing, testing and securing smart
contracts, and eventually build their own learning levels and simulated
economic worlds.

Every one of those ideas needs the same foundation: a world whose rules are
explicit, whose state changes are validated and recorded, and whose history can
be replayed exactly. **v0.1 builds only that foundation.** It has no tokens,
wallets, smart contracts, blockchain nodes, graphics, multiplayer or live
language-model agents, but the agent interface is designed so those can be
added later without rewriting the engine (see [Agents](#agents-and-future-llm-adapters)).

## Quick start (Windows PowerShell)

With [uv](https://docs.astral.sh/uv/) (recommended; it can download Python 3.12 for you):

```powershell
cd D:\Github\project-genesis
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe main.py demo
```

With a python.org installation of Python 3.12 instead:

```powershell
cd D:\Github\project-genesis
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe main.py demo
```

The commands call the virtual environment's Python directly, so no activation
is needed. If you prefer to activate it (`.\.venv\Scripts\Activate.ps1`), the
installed `genesis` command replaces `python main.py` everywhere below.

## The demo

`python main.py demo` creates a fresh world (seed 42), simulates 100 days, audits
the complete event log and prints the result:

```text
Project GENESIS v0.1.0 demo: 20 residents, seed 42, 100 days

 day  pop    food $    wood $   stone $  trades  units      value  health   gini
--------------------------------------------------------------------------------
  10   20      2.29      3.24      4.14      40     40     126.15   100.0  0.057
 ...
 100   20      2.29      3.24      4.14      38     38     119.72   100.0  0.308

GENESIS world - day 100, seed 42
Population: 20 alive, 0 dead (of 20)
Occupations: farmer 5  woodcutter 7  miner 8
Market prices (credits/unit): food 2.29  wood 3.24  stone 4.14
Resources held, all residents: food 147  wood 169  stone 176
Resources held, living only:   food 147  wood 169  stone 176
Produced to date: food 2,047  wood 2,069  stone 2,046
Consumed to date: food 2,000  wood 2,000  stone 1,970
Money supply: 2,000.00 credits (constant; 2,000.00 held by the living)
Transactions: 3,867 trades, 3,890 units, 12,350.97 credits
Wealth of living residents (cash + inventory at market prices, credits):
  mean 180.64  median 196.08  min 46.89  max 428.66
  Gini 0.308  richest 10% hold 20.1%  poorest 50% hold 26.8%
Mean health of the living: 100.0
Event log: 7,649 events   State digest: 8ed4e8d7dd86fafc

Invariants: OK (holdings non-negative, money and resources conserved, event log audit passed)
```

The state digest is a SHA-256 of the entire world, event log included. Seed 42
after 100 days gives `8ed4e8d7dd86fafc...` on every machine and every Python
version tested (3.12, 3.13, 3.14), so it doubles as a reproducibility check. Try
`demo --seed 7 --days 365` for a longer run.

## Command-line interface

Worlds are saved in a SQLite file, `genesis_world.db` by default (override with
`--db PATH` or the `GENESIS_DB` environment variable).

```powershell
python main.py init --seed 42                 # create a new world (refuses to overwrite)
python main.py advance --days 100             # simulate and save
python main.py status                         # population, prices, holdings, trades, wealth
python main.py residents --sort wealth        # every resident in a table
python main.py inspect 3 --events 15          # one resident in detail, with recent events
python main.py report --format json --output reports\day100.json
python main.py report --format csv --table daily --output reports\daily.csv   # or residents, trades
python main.py verify                         # replay the whole event log and check every invariant
python main.py reset                          # start over at day 0 (asks you to type 'reset'; --yes skips)
python main.py demo --days 100 --seed 42      # in-memory demonstration
```

`advance` refuses to save a world whose invariants fail, and `reset` and `init`
refuse to touch any file that is not a GENESIS save.

## Web3 scenario harness (Phase 1)

A scenario is a versioned manifest under [`scenarios/`](scenarios): learning
objectives, starting accounts, the expected transaction and grading criteria.
The harness starts a private Anvil chain on `127.0.0.1`, puts it in the
scenario's starting state, has an actor submit the transaction, grades the
receipt and balances with a deterministic judge, writes a JSON report, and
restores the starting state. Phase 1 contains one scenario and one actor (the
scripted reference solution). There are no keys, wallets, public networks or
model calls. See [docs/HARNESS_ARCHITECTURE.md](docs/HARNESS_ARCHITECTURE.md)
for the design and [docs/SCENARIO_FORMAT.md](docs/SCENARIO_FORMAT.md) for the
manifest and report formats.

**Install Foundry (for `anvil`).** Per the [Foundry installation
guide](https://getfoundry.sh/introduction/installation), `foundryup` runs in
Git Bash or WSL, not in PowerShell or Command Prompt. In **Git Bash**:

```bash
curl -L https://foundry.paradigm.xyz | bash
```

Restart Git Bash, then run `foundryup`. Alternatively, download a precompiled
release from [github.com/foundry-rs/foundry/releases](https://github.com/foundry-rs/foundry/releases)
(for Windows, `foundry_<version>_win32_amd64.zip`), check its SHA-256 against
the `.sha256` file published next to it, and extract it into
`%USERPROFILE%\.foundry\bin`, the folder `foundryup` uses. The harness was
verified this second way, with Foundry v1.8.7.

Put the folder on `PATH` for the current PowerShell session, then check:

```powershell
$env:Path = "$env:USERPROFILE\.foundry\bin;$env:Path"
```

```powershell
anvil --version
```

To make it permanent, add `%USERPROFILE%\.foundry\bin` to your user `PATH` in
Windows' environment-variable settings. Without `PATH`, pass the executable
explicitly: `--anvil "$env:USERPROFILE\.foundry\bin\anvil.exe"`.

**Use it** (from the repository root):

```powershell
.\.venv\Scripts\python.exe main.py scenario list
.\.venv\Scripts\python.exe main.py scenario validate first-local-transfer
.\.venv\Scripts\python.exe main.py scenario run first-local-transfer                      # writes reports\first-local-transfer.json
.\.venv\Scripts\python.exe main.py scenario run first-local-transfer --repeat 3           # reset between runs, compare outcomes
.\.venv\Scripts\python.exe main.py scenario run first-local-transfer --value "1 ether"    # a deliberate mistake: graded as failed
Get-Content reports\first-local-transfer.json
```

The exit code is 0 only when the scenario passed; `failed` and `rejected` runs
exit with 1. Without Foundry, `scenario run` stops with an `error` report that
says what to install. [docs/examples/first-local-transfer.report.json](docs/examples/first-local-transfer.report.json)
is a real report from Anvil 1.8.7.

**Tests.** The harness's unit tests use an in-repository test double of the
few Anvil RPC methods involved, served over real HTTP, so they run without
Foundry. The integration tests start a real `anvil` and are skipped, with the
reason printed, when it is not on `PATH`:

```powershell
.\.venv\Scripts\python.exe -m pytest                  # everything; Anvil tests skip if anvil is missing
.\.venv\Scripts\python.exe -m pytest -m anvil         # only the real-Anvil integration tests
.\.venv\Scripts\python.exe -m pytest -m "not anvil"   # everything except them
```

Verified on Windows 11 with Python 3.12.14 and Anvil 1.8.7: all three
integration tests pass. Real Anvil and the test double produce the same
normalized digest for the reference run, which a pinned test checks on both.

**Anvil-local only.** Nothing has been run against Monad Testnet or any other
public network, and no compatibility with them is claimed. A public test
network needs real keys, faucet funds and permanent transactions, so it will
get its own adapter and its own tests (see the architecture document).

## How it works

```text
             +------------------- one day -------------------+
 Observation |  1 decide     agents propose a Decision        |
  (a copy)   |  2 occupations validated: cooldown, existence   |
     |       |  3 production  work -> output (seeded RNG)      |
     v       |  4 market     escrow -> call auction -> settle  |
   Agent ----+  5 consumption needs -> health -> death         |
  proposes   |  6 bookkeeping stats + invariant check          |
             +-----------------------------------------------+
                  every balance change -> append-only event log
```

| Module | Responsibility |
| --- | --- |
| [`models.py`](genesis/models.py) | Plain data types: resources, residents, events, config, and the agent interface (`Observation`, `Decision`, `OrderRequest`) |
| [`world.py`](genesis/world.py) | The authoritative world state, world creation, seeded RNG streams, state digest |
| [`agents.py`](genesis/agents.py) | The `Agent` protocol and the transparent `RuleBasedAgent` |
| [`economy.py`](genesis/economy.py) | Economic rules: production, consumption, order validation and escrow, the call auction, settlement, prices, wealth statistics |
| [`simulation.py`](genesis/simulation.py) | The daily loop that turns proposals into validated, recorded state changes |
| [`invariants.py`](genesis/invariants.py) | State invariants and the independent event-log audit |
| [`persistence.py`](genesis/persistence.py) | Versioned SQLite save files |
| [`reporting.py`](genesis/reporting.py) | Text summaries, JSON reports, CSV tables |
| [`cli.py`](genesis/cli.py) | The command-line interface |

The economic rules, the rule-based policy, measured behaviour and limitations
are documented in **[docs/ECONOMY.md](docs/ECONOMY.md)**. The save file schema
is documented in **[docs/SAVE_FORMAT.md](docs/SAVE_FORMAT.md)**.

## Guarantees and how they are tested

| Guarantee | How it is enforced and tested |
| --- | --- |
| No negative cash or inventory, ever | Orders are escrowed at validation; settlement re-checks; daily invariant check; SQLite `CHECK` constraints; the audit replays every event and checks every intermediate balance |
| Money is conserved | No mechanism creates or destroys money; `sum(cash) == money_supply` is checked every day |
| Resources are conserved and accounted | `holdings == initial + produced - consumed` every day; production and consumption cross-checked three ways (ledger, events, daily stats) |
| Trades are consistent | One uniform price per auction, within every matched limit; no self-trades; no order over-filled; volume maximal (property-tested on 300 random order books) |
| The event log is complete | `audit_event_log` rebuilds every balance from the genesis allocation and must match the state exactly; tampering tests prove it notices |
| Deterministic replay | Same seed and config give an identical world and event log; a golden digest pins seed 42 at day 100 |
| Save/load is lossless | Round trips preserve the digest; saving at day 50 and continuing equals an uninterrupted 100-day run |
| The engine is authoritative | Tests with agents that raise, return garbage, overspend, oversell, thrash occupations or act randomly: everything invalid is rejected and logged, and the invariants hold |

Run them with `python -m pytest` (about 430 tests, under 20 seconds).

**Determinism in detail.** Randomness comes only from `random.Random` instances
derived from `(seed, day, purpose)`, never from the global generator, so phases
cannot disturb each other's random numbers and a loaded world continues exactly
as if it had never been saved. The engine uses integer arithmetic throughout,
iterates in fixed orders, and policies must be deterministic functions of their
observation.

## Agents and future LLM adapters

An agent is anything with `decide(observation) -> Decision`. Agents never see
the world, only a private copy of what their resident may know, and every part
of every decision is validated by the engine. A language-model agent is
therefore just another policy:

```python
import json

from genesis.models import Decision, Observation
from genesis.simulation import Simulation
from genesis.world import create_world


class LanguageModelAgent:
    """Sketch of a future adapter: Claude, GPT, Gemini, or a local model."""

    def __init__(self, complete):  # complete: prompt text -> reply text
        self.complete = complete

    def decide(self, observation: Observation) -> Decision:
        prompt = (
            "You are a resident of a small town. Reply with JSON of the form "
            '{"activity": "work"|"rest", "new_occupation": null|"farmer"|..., '
            '"orders": [{"side", "resource", "quantity", "limit_price"}]}.\n'
            + json.dumps(observation.to_dict())
        )
        return Decision.from_dict(json.loads(self.complete(prompt)))


def my_model(prompt: str) -> str:
    raise NotImplementedError("call your language model here")


world = create_world(seed=1, policy="llm")
simulation = Simulation(world, {"llm": LanguageModelAgent(complete=my_model)})
```

Invalid replies are handled by the engine: an exception or a non-`Decision`
becomes an `agent_error` event and the default decision (work, no orders);
invalid orders and actions become `order_rejected` and `action_rejected` events.
Different residents can use different policies in the same world. For exact
replays, an adapter should be deterministic (e.g. temperature 0) or record its
replies.

## Running on an Ubuntu home server

Ubuntu 24.04 ships Python 3.12. The simulation is single-threaded and light:
on a desktop CPU, 1,000 simulated days take about 2 seconds and about 40 MB of
RAM (the whole event log is kept in memory), and saving or loading a
1,000-day world takes 1-2 seconds.

```bash
sudo apt install python3.12-venv
python3.12 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest
genesis demo            # should print the same state digest as on Windows
genesis init --db /srv/genesis/world.db
genesis advance --db /srv/genesis/world.db --days 1   # e.g. from a daily cron job or systemd timer
```

## Limitations of v0.1

The full list is in [docs/ECONOMY.md](docs/ECONOMY.md#known-limitations). In short:
the mechanics are deliberately simplified (fixed needs, no capital, credit,
wages, births or inheritance, one market, T+1 settlement), prices are sticky in
the default world, and inequality drifts upward over long runs. The outcomes
described above are measured properties of the default configuration, not
guarantees. In addition, each save rewrites the full snapshot and the whole
event log is held in memory, which is fine for thousands of days but not for
millions of events.

## Roadmap

Each step builds on the engine's guarantees rather than bypassing them.

1. **Engine:** incremental event storage, more goods and production chains,
   durable goods, inheritance and births, configurable scenarios.
2. **Agents:** language-model adapters behind the existing `Agent` protocol,
   with recorded replies for exact replay; agent memory; experiment tooling to
   compare policies.
3. **Scenario harness:** more scenarios on the Phase 1 foundation (reading
   receipts, contract calls, events); a learner interface that acts as an
   `Actor`; a separate Monad Testnet adapter with its own key handling and
   tests; optional AI-agent evaluation by adding model adapters as actors.
4. **Learning world:** levels and quests as scripted scenarios, a knowledge map,
   and AI NPC mentors that explain what happens in the simulation.
5. **Web3 layer:** simulated ledgers, tokens and contracts inside the sandbox,
   then interactive on-chain experiments on test networks, with security
   lessons built in.
6. **Creation:** tools for players to build their own levels and economic worlds.

## License

Not chosen yet. Pick an open-source license (for example MIT or Apache-2.0)
and add a `LICENSE` file before publishing.

## Security Diagnostic Lab (Phase 2)

The browser mission, The Wrong Recipient, connects to the local authoritative mission API. See [setup and acceptance steps](docs/SECURITY_LAB.md). Build with `npm --prefix frontend run build` and launch with `.\.venv\Scripts\python.exe -m genesis.lab`.


The mission is played as a 2D pixel investigation game in Simplified Chinese, 「错付疑云」. Walk the detective between Alice's studio, the payment relay, Bob's atelier, the chain archive and the wallet terminal. Collect evidence, compare the complete addresses and pick a validation rule. Then watch where the real local-chain transfers go. Everything shown comes from the backend. What was and was not verified (desktop and an emulated iPhone viewport in Chromium; no real iPhone) is recorded in [docs/SECURITY_LAB.md](docs/SECURITY_LAB.md#pixel-investigation-game-frontend-2026-11-03). Screenshots are in [docs/screenshots](docs/screenshots). Open backend requests from the frontend are in [docs/FRONTEND_BACKEND_REQUESTS.md](docs/FRONTEND_BACKEND_REQUESTS.md).
