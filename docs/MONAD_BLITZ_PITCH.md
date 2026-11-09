# Monad Blitz pitch — Project GENESIS on Monad Testnet

One line: **civilisations rise and fall in 3 minutes — bet on the survivor;
every epoch ends in a hash anyone can recompute. Not GameFi — no token, no
speculation.**

一句话：文明三分钟兴衰——押注幸存者；每个纪元都以一个任何人都能重算的
哈希收尾。不是 GameFi——没有代币，没有投机。

## What it is

One epoch is four civilisations racing in parallel — Aurora, Boreas,
Cinder, Dune — each a real 60-day mini-world with 5 residents, run through
the real simulation engine. Before the epoch runs, you bet play-money
points (演示积分 · 不是真钱) on the civilisation you think survives best.
The winner is the highest survival score — `alive × 1,000,000 +
wealth_cents + total_health × 100`, population first — with ties broken by
the smallest `SHA-256("genesis:epoch-winner:<epoch_digest>:<civ_id>")`.
Settlement is parimutuel with house fee 0: winners split the whole pool
in proportion to stake; if nobody backed the winner, every stake is
refunded in full. The epoch ends in one digest — SHA-256 of canonical JSON
over the parameters plus each civilisation's id, name, seed, world digest
and score inputs — that anyone can recompute. The full loop design is in
[docs/EPOCH_BETTING.md](EPOCH_BETTING.md); the 60-second hands-on demo is
in [docs/DEMO_SCRIPT.md](DEMO_SCRIPT.md).

## The 60-second demo

1. **Bet (0:00–0:10).** One command, no wallet, no key, no network:
   `python main.py epoch --bet you:2:100` — 100 play credits on Cinder.
2. **Run the epoch (0:10–0:35).** Four 60-day worlds run in about a
   second. Read the JSON live: all four end with 5 alive, and **Cinder
   wins** with 5,144,627 — Aurora 5,143,163, Boreas 5,144,121, Dune
   5,143,061. Cinder wins by 506 points, on wealth (94,627 vs 94,121).
   Epoch digest `b25c8fb3e94f746bf4d29fd7118ecd0fb72b23b8386eda76b35830e00cfab9fc`.
3. **Settle and prove (0:35–0:55).** Pool 100, winner pool 100, payout
   100 — settled in the open, from the same numbers everyone just watched.
   Then the anchor: the seed-42, 100-day world digest `8ed4e8d7dd86fafc`
   is already in `GenesisLedger`
   (`0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`, anchor tx
   `0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f`).
   Read it back live — no key, no spending:
   `cast call 0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1 "getDigest(uint256)(bytes32)" 100`
   — the digest comes back `0x8ed4e8d7dd86fafc…`.
4. **Close (0:55–1:00).** One line, then invite the room to name a seed
   and watch it run.

If there are 3 minutes, change the inputs and watch the outcome change:
`--seed 43` → **Boreas** wins (digest `6561439a3eb4eb79…`);
`--max-orders 2` → all four civilisations starve (0 alive, all scores 0)
and the winner is decided purely by the digest-hash tiebreak — **Dune**.
Every change moves the digest, because the world really changed.

## Why this wins (and what to say when asked)

- **Determinism is the product.** Most hackathon demos are a UI on top of
  a chain. This one is a world with provable history: every event is
  logged, every invariant is checked, the whole epoch hashes to one
  digest — and the bet makes the determinism *matter*, because the outcome
  is unknown until the epoch runs and undeniable after it.
- **The chain is the proof, not the database.** The simulation stays
  off-chain and reproducible; Monad stores only the anchor. That is why it
  is cheap, fast, and honest about what a chain is for. And the loop needs
  Monad's fast finality: an epoch settles and the next one starts, so
  settlement must finalise quickly — Monad's fast blocks and parallel
  execution give the loop that pace.
- **It teaches.** The harness is a learning platform: versioned scenarios,
  a deterministic judge, the same rules for a person and for an AI agent.
  Monad is where the learner's first real transaction happens — and the
  scenario explains, before they run it, that it is permanent. The betting
  loop teaches the same lesson in miniature: a prediction, an outcome, and
  a proof you can check yourself.
- **It is real, and it says so — with live transactions to prove it.**
  The first live Monad Testnet transfer has happened and passed 13/13
  (`first-monad-transfer`): 1.5 MON from
  `0xE705B6cDfDc682bE49bdDa177A695207ff67Bf35` to
  `0xEa3C22fE64eF4BfAf0fE58F49b7dF5fC5ABA3A09`, tx
  `0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11`,
  block 78228932, fee 0.002415 MON (21,000 gas @ 115 Gwei). Sender
  5 → 3.497585 MON, receiver 0 → 1.5 MON. Verify it:
  https://testnet.monadexplorer.com/tx/0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11
  The adapter, the scenario and the contract are tested offline (614 tests
  passing); the live run is done, and the ledger is deployed and anchored:
  contract `0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`, anchor tx
  `0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f`
  (seed 42, day 100, 20 residents, 3,867 trades). The wallet holds 3.4323
  MON after the transfer, the deploy and the anchor. All live-chain facts
  are shared from one source of truth, `frontend/chain.json`.
- **The anchor is live and readable.** `GenesisLedger` is deployed at
  `0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`; anyone can read the anchored
  digest back with
  `cast call 0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1 "getDigest(uint256)(bytes32)" 100`
  and compare it with a local `python main.py demo` run — or verify a
  transaction read-only with
  `python main.py monad verify --tx 0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11`,
  or print the whole fact sheet with `python main.py epoch --real-testnet`
  (which places no bet and claims no payout).

## Rubric → evidence

Blitz has **no published weighted rubric** — the criteria below are the
peer-vote dimensions the event is judged on, and the mapping is ours, not
an official scoring sheet. Nothing here claims a weight or a score.

| Peer-vote criterion | Evidence in this entry |
| --- | --- |
| **Novelty & Originality** | A bet on *simulated civilisations*, not a price or a match: the thing you bet on is a set of whole worlds, and the settlement proof is a recomputable hash of those worlds. The chain stores no game state — only one digest as proof. |
| **Innovative Mechanics leveraging Monad** | The loop is built around what Monad is fast at: an epoch settles and the next starts, so settlement needs fast finality — Monad's fast blocks and parallel execution give the loop its pace, and the anchor is one cheap write (live transfer fee: 0.002415 MON). The simulation stays off-chain; Monad is the proof layer, not the database. |
| **Problem-Solving** | Two real problems, one slice: hackathon demos are usually unverifiable (recorded screens, hard-coded numbers) — here the judge re-runs one command and the digest must match; and a beginner's first on-chain step is scary and irreversible — here the bet is play-money by default and the learning scenarios grade every step deterministically before anything real happens. |
| **Learning & Experimentation** | The whole entry is a learning instrument: versioned scenarios with a deterministic judge (local Anvil first, then the same transfer live on Monad Testnet), a playable epoch where changing the seed or the market changes the winner (`--seed 43` → Boreas; `--max-orders 2` → all starve, tiebreak picks Dune), and a verification step anyone can repeat — 614 tests passing, 3/3 golden epochs bit-for-bit in the browser port, every number in the demo recomputable. |

## Before the event

- [x] Fund a key from https://faucet.monad.xyz
- [x] Replace `alice` in `scenarios/first-monad-transfer/scenario.toml` with
      the key's address; set `bob` to a fresh address
- [x] Do one live scenario run and keep the explorer link — DONE 13/13:
      tx `0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11`,
      block 78228932, 1.5 MON, fee 0.002415 MON
      (https://testnet.monadexplorer.com/tx/0x4b66b46fba5301e60452ae5d38c5e58e4f636302b7f80425777ef1a4355eae11)
- [x] Deploy `GenesisLedger` (`contracts/README.md`) and set
      `GENESIS_MONAD_LEDGER` — DONE: contract
      `0x0D903C5f9ae82e52aA69D39068EF80B85fAFaBA1`, deployment tx
      `0xfc042b3927ea880c6517c1c6f20e458ef8b366cc6f1a8ca0dc0f9220e7170c00`;
      anchor done, tx
      `0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f`
      (https://testnet.monadexplorer.com/tx/0xd035cdda274104d6958300f0022562a3cebde1e3f370d49fe2061bcad5fc433f)
- [ ] Rehearse the 60-second demo in [docs/DEMO_SCRIPT.md](DEMO_SCRIPT.md),
      in order, with the terminal visible

## What not to claim

- Never claim a gas fee other than the measured one: the live transfer paid
  0.002415 MON (21,000 gas @ 115 Gwei).
- The live claims you *can* make are the transfer above, with its real
  transaction hash, block number and explorer link, and the anchor
  (`0xd035cdda…fc433f`, contract `0x0D903C…ABA1`) — both public on the
  explorer.
- Never call it GameFi and never imply real-money betting: play-money by
  default, no token, no speculation; the real-testnet mode is optional and
  labelled.
- Never claim a rubric weight or a score: Blitz publishes no weighted
  rubric; the table above maps the peer-vote criteria to evidence only.
- Never describe the epoch with other rules: it is 4 civilisations
  (Aurora, Boreas, Cinder, Dune), 5 residents each, 60 days by default
  (30–90); winner by survival score with the digest-hash tiebreak;
  settlement parimutuel, house fee 0, full refund when nobody backed the
  winner. See [docs/EPOCH_BETTING.md](EPOCH_BETTING.md).
