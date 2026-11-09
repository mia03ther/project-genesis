# Project GENESIS

**Civilisations rise and fall in 3 minutes — bet on the survivor; every
epoch ends in a hash anyone can recompute.**

**文明三分钟兴衰——押注幸存者；每个纪元都以一个任何人都能重算的哈希收尾。**

**不是 GameFi —— 没有代币，没有投机。** *Not GameFi — no token, no
speculation.* Bets are play-money points by default. There is no token, no
real-money wagering, no earning mechanism. An optional real-testnet mode is
clearly labelled and uses test MON only, on Monad Testnet, with a funded
key — never by default, never with real money.

GENESIS is a deterministic, programmable civilization simulation: a small
economy of 20 autonomous residents who produce, trade and consume food,
wood and stone in a daily market. The engine is authoritative, every run is
exactly reproducible from its seed, and the books always balance. The
**betting loop** turns that world into a game a stranger can play in 60
seconds: one epoch is four civilisations racing in parallel — Aurora,
Boreas, Cinder, Dune — each a real 60-day mini-world with 5 residents;
before the epoch runs you bet play-money on the civilisation you think
survives best; when the epoch ends, the bets settle in the open and the
whole epoch hashes to one digest that anyone can recompute. See
[docs/EPOCH_BETTING.md](docs/EPOCH_BETTING.md) for the loop design.

Alongside it, the **scenario harness** (Phase 1) runs versioned Web3
learning scenarios on a private local Anvil chain and grades them
deterministically. It starts with *First Local Blockchain Transfer*.

It is written in plain Python 3.12 with only the standard library at
runtime (SQLite included); `pytest` is the only development dependency.
The harness additionally needs Foundry's `anvil` to run scenarios on a
real local chain.

## Why this fits Monad Blitz

A simulated world is cheap to run and worthless as a claim — anyone can
say "my simulation did this". The chain turns the simulated world into a
provable fact: one digest, anchored once, readable by anyone, forever.
That is the entire job the chain does here, and it is the job a chain is
for. The loop is small on purpose: one bet, one epoch, one hash — a judge
can verify the whole thing in under a minute with one command and one
explorer link.

The Monad property the loop needs is **fast finality**: an epoch settles
and the next one starts, so settlement must finalise quickly or the loop
stalls between rounds. Monad's fast blocks and parallel execution give
that finality — the anchor is one cheap write that confirms quickly, and
many epochs can settle without queueing behind each other. The simulation
stays off-chain and reproducible; Monad stores only the anchor.

## The betting loop in 60 seconds

No keys, no wallet, no network. From the repository root, one command
runs an epoch with bets and prints the whole result as JSON:

```bash
python main.py epoch --bet you:2:100
```

1. **Bet.** Back a civilisation with play-money points
   (演示积分 · 不是真钱), in integer cents: `--bet PLAYER:CIV:AMOUNT`,
   repeatable — e.g. `--bet alice:2:100 --bet bob:0:100`. Civilisations
   are 0 Aurora, 1 Boreas, 2 Cinder, 3 Dune.
2. **Run the epoch.** Four 60-day mini-worlds run through the real engine
   (civilisation `i` uses seed `epoch_seed × 1000 + i`). Default epoch
   (`epoch:42:60:4:5:0:10`): all four end with 5 alive, and **Cinder wins**
   with survival score 5,144,627 — Aurora 5,143,163, Boreas 5,144,121,
   Dune 5,143,061. The winner rule is public: `alive × 1,000,000 +
   wealth_cents + total_health × 100` — one extra survivor outweighs any
   wealth gap. Ties are broken by the smallest
   `SHA-256("genesis:epoch-winner:<epoch_digest>:<civ_id>")`, a pure
   function of the digest.
3. **Settle.** Parimutuel, house fee 0: winners split the whole pool in
   proportion to stake (`stake × pool // winner_pool`, leftover cents to
   the earliest winning bets, so payouts always sum to the pool exactly).
   Verified example: 100 on Cinder and 100 on Aurora → pool 200, Cinder
   wins, the Cinder bet pays 200. If nobody backed the winner, every stake
   is refunded in full — nothing rolls over.
4. **Verify.** The epoch ends in one digest — SHA-256 of canonical JSON
   over the parameters plus each civilisation's id, name, seed, world
   digest and score inputs. Re-run the same epoch and the digest must
   match: default digest
   `b25c8fb3e94f746bf4d29fd7118ecd0fb72b23b8386eda76b35830e00cfab9fc`.
   The JavaScript port in `frontend/engine.js` reproduces it bit-for-bit
   (`node frontend/verify_epochs.mjs`: 3/3 golden epochs, winner + payouts
   identical).

Change the seed and the winner changes — seed 43 → **Boreas** wins
(digest `6561439a3eb4eb79`). Change a policy and the outcome changes too:
`--max-orders 2` starves every civilisation (all 0 alive, all scores 0)
and the winner is decided purely by the digest-hash tiebreak — **Dune**.
That is why the bet is real: the worlds are deterministic, but nobody
knows the outcome until the epoch runs. The browser playground runs the
same engine — open it with `cd frontend && python -m http.server` — and
`python main.py epoch --real-testnet` prints the verified Monad Testnet
facts instead of running an epoch (it places no bet and claims no payout).

## Vision

GENESIS is meant to grow into an AI-native world you can learn in and
experiment with: a sandbox where autonomous agents, including
language-model agents, live in a simulated economy; a research platform
for studying those agents; and, ultimately, a gamified learning world for
Web3. The betting loop is the first playable slice of that world — a
small, sharp entry point that proves the pattern (playable world +
recomputable proof) before anything bigger is built on it.

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

## The demo — one epoch, end to end

`python main.py demo` creates a fresh world (seed 42), simulates 100 days,
audits the complete event log and prints the result. This is the same epoch
the betting loop plays — the command-line twin of the browser playground:

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

## Frontend — the betting table

There is a static, no-build-step playground in [`frontend/`](frontend/):
world overview, a day-by-day replay (Day 10 / 50 / 100 with a real Gini
chart), the market, the residents ranked by wealth, and the on-chain
anchor panel for the world digest. It runs the same engine in the browser
— change the seed, the tax rate or the market, and the world recomputes
with a new digest. Run the same parameters with `python main.py play`
and the digest must match. The browser also implements the betting loop:
`frontend/engine.js` carries the same epoch API as the Python engine
(`runEpoch`, `deriveWinner`, `survivalScore`, `placeBet`, `settleEpoch`),
verified against the Python implementation
(`node frontend/verify_epochs.mjs`: 3/3 golden epochs, winner + payouts
bit-for-bit; `node frontend/verify_engine.mjs`: 10/10 golden worlds).

```bash
cd frontend
python -m http.server    # then open http://localhost:8000
```

Or just double-click `frontend/index.html` — it works from `file://` too.

Every number on the page comes from the real demo run, generated by
[`frontend/generate_data.py`](frontend/generate_data.py), which runs the
engine (seed 42, 100 days) and refuses to write anything unless the state
digest still matches the golden `8ed4e8d7dd86fafc`. Regenerate after any
engine change:

```bash
python frontend/generate_data.py   # rewrites frontend/data.json + data.js
```

The anchor panel shows the digest and the live anchor: contract
`0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`, anchor transaction
`0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f`,
with explorer links. (Screenshot: not included yet — open the page and
take one.)

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
python main.py play --seed 42 --days 100 --tax-bps 0 --max-orders 10   # one epoch: JSON summary with digest (the betting loop's CLI twin)
python main.py epoch --bet alice:2:100 --bet bob:0:100   # run a betting epoch (play money) and settle it; --real-testnet prints the verified Monad facts instead
python main.py monad verify --tx 0x...   # read-only: verify a Monad Testnet transaction, no key
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

## Monad Testnet

The harness now has a **separate Monad Testnet adapter** (`genesis/harness/monad.py`),
a second scenario, and a contract that anchors a world's digest on-chain. It is
a separate adapter, never a flag on the Anvil one: keys, signing, funding,
confirmation and the no-reset rule all live there, with their own tests.

**What runs offline, today.** The new scenario `first-monad-transfer` (a 1.5 MON
transfer, graded 13/13 by the same judge) validates and passes against a local
test double or an `anvil` node started with `--chain-id 10143`, with no key:

```powershell
.\.venv\Scripts\python.exe main.py scenario validate first-monad-transfer
.\.venv\Scripts\python.exe main.py scenario run first-monad-transfer --rpc-url http://127.0.0.1:8545
```

The contract `contracts/GenesisLedger.sol` compiles with Foundry 1.9.0
(`cd contracts && forge build`).

**What runs live, today.** The first live Monad Testnet transfer has
happened and passed 13/13 (`first-monad-transfer`): 1.5 MON from
`0xE705B6cDfDc682bE49bdDa177A695207ff67Bf35` to
`0xEa3C22fE64eF4BfAf0fE58F49b7dF5fC5ABA3A09`, transaction
`0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11`,
block 78228932, fee 0.002415 MON (21,000 gas @ 115 Gwei). Sender
5 → 3.497585 MON, receiver 0 → 1.5 MON. Verify it:
https://testnet.monadexplorer.com/tx/0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11

**Anchor: done, on-chain.** The `GenesisLedger` contract is deployed on
Monad Testnet at `0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`
(deployment tx
`0xfc042b3927ea880c6517c1c6f20e458ef8b366cc6f1a8ca0dc0f9220e7170c00`),
and the seed-42, 100-day world digest `0x8ed4e8d7dd86fafc…` is anchored in
it (day 100, population 20, trades 3,867), anchor tx
`0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f`:
https://testnet.monadexplorer.com/tx/0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f

Read it back yourself — no key, no spending:

```bash
cast call 0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1 "getDigest(uint256)(bytes32)" 100 --rpc-url https://testnet-rpc.monad.xyz
# 0x8ed4e8d7dd86fafce0ec09064a239b599d0eb596f4588d69b249cbbd1ad201c6
```

That value must equal the digest of a local `python main.py demo` run —
that equality is the whole proof. To anchor a different world of your own:

```bash
python main.py monad anchor --digest 0x<your digest> --day 100 --population 20 --trades 3867 --contract 0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1
```

**Hackathon demo.** For the Monad Blitz judge demo, follow the 60-second
hands-on script in [docs/DEMO_SCRIPT.md](docs/DEMO_SCRIPT.md) — bet,
watch the epoch, settle, verify the digest on-chain — and the one-page
pitch in [docs/PITCH_ONEPAGE.md](docs/PITCH_ONEPAGE.md). The loop design
is in [docs/EPOCH_BETTING.md](docs/EPOCH_BETTING.md).

**Live proof.** The first live Monad Testnet transfer passed 13/13
(1.5 MON, tx
`0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11`,
block 78228932) and the seed-42, 100-day world digest is anchored in
`GenesisLedger` (anchor tx
`0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f`).
Verify either read-only, with no key and no spending:
`python main.py monad verify --tx 0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11`
or `python main.py epoch --real-testnet`.
The wallet holds 3.4323 MON after the transfer, the deploy and the
anchor. Full test suite: 614 passed, 0 failed.

**How to repeat the live run yourself.** A live run needs a funded key,
which this repository does not contain:

1. Get free test MON from the faucet: https://faucet.monad.xyz
2. Put the key in the environment (never in a file, never on the command line
   if you can avoid it): `GENESIS_MONAD_PRIVATE_KEY=0x...`
3. Replace the `alice` address in `scenarios/first-monad-transfer/scenario.toml`
   with your key's address, and use a fresh address for `bob`.
4. Run it — once only, it cannot be repeated or undone:
   `python main.py scenario run first-monad-transfer`
5. Deploy the ledger and anchor a world:
   `cd contracts && forge create --rpc-url https://testnet-rpc.monad.xyz --private-key "$GENESIS_MONAD_PRIVATE_KEY" GenesisLedger.sol:GenesisLedger`
   then `python main.py monad anchor --digest 0x<demo digest> --day 100 --population 20 --trades 3867 --contract 0x<deployed address>`

Monad Testnet is chain id
10143, RPC `https://testnet-rpc.monad.xyz`. See `docs/HARNESS_ARCHITECTURE.md`
for how the adapter differs from Anvil, and `contracts/README.md` for the
deploy steps.

**Why Monad changes the demo.** On Anvil a world is private and disposable;
on Monad Testnet a world's digest is public and permanent. Anyone can re-run
the same seed locally and check that their digest matches the anchored one —
the chain becomes the proof that a particular world existed. That is the
hackathon centrepiece: a deterministic world, anchored in public. And the
loop needs Monad's fast finality: an epoch settles and the next one starts,
so settlement must finalise quickly — fast blocks and parallel execution
give the loop that pace.


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

Run them with `python -m pytest` (614 tests, all passing).

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
   `Actor`; the Monad Testnet adapter is done (signed transfers via `cast`,
   `first-monad-transfer`, and the `GenesisLedger` anchor contract) — the
   first live transfer has run and passed 13/13 on Monad Testnet, the ledger
   is deployed at `0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`, and the
   seed-42 world digest is anchored in it (anchor tx
   `0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f`);
   optional AI-agent evaluation by adding model adapters as actors.
4. **Learning world:** levels and quests as scripted scenarios, a knowledge map,
   and AI NPC mentors that explain what happens in the simulation.
5. **Web3 layer:** simulated ledgers and contracts inside the sandbox,
   then interactive on-chain experiments on test networks, with security
   lessons built in. Still no token: the betting loop stays play-money,
   with testnet mode optional and labelled.
6. **Creation:** tools for players to build their own levels and economic worlds.

## License

Not chosen yet. Pick an open-source license (for example MIT or Apache-2.0)
and add a `LICENSE` file before publishing.
