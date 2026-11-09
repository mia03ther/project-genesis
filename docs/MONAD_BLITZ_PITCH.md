# Monad Blitz pitch — Project GENESIS on Monad Testnet

One line: **a deterministic civilization you can re-run anywhere, with its
history anchored in public on Monad.**

## The 60-second demo

1. **Run the world.** `python main.py demo` — 20 residents, 100 days, seed 42.
   The state digest is `8ed4e8d7dd86fafc` on every machine. Say it out loud:
   "same seed, same world, every time."
2. **Show the local scenario.** `python main.py scenario run first-local-transfer`
   — 13/13, receipt, gas, nonce. This is the learning loop: do it, read the
   receipt, get graded.
3. **Go public.** `python main.py scenario run first-monad-transfer` — the
   same transfer, the same judge, but a real transaction on Monad Testnet.
   The report prints the explorer link. Open it. That is the moment: the
   transfer is permanent and public, and it cannot be reset.
4. **Anchor the world.** `python main.py monad anchor --digest 0x8ed4e8d7... --day 100 --population 20 --trades 3867`
   — the world's digest lands in `GenesisLedger` on Monad Testnet. Then:
   `cast call <contract> "getDigest(uint256)(bytes32)" 100` — the digest
   comes back. Anyone in the room can re-run the demo with seed 42 and check
   that their digest matches the anchored one.

## Why this wins (and what to say when asked)

- **Determinism is the product.** Most hackathon demos are a UI on top of a
  chain. This one is a world with provable history: every event is logged,
  every invariant is checked, the whole state hashes to one digest.
- **The chain is the proof, not the database.** The simulation stays
  off-chain and reproducible; Monad stores only the anchor. That is why it
  is cheap, fast, and honest about what a chain is for.
- **It teaches.** The harness is a learning platform: versioned scenarios,
  a deterministic judge, the same rules for a person and for an AI agent.
  Monad is where the learner's first real transaction happens — and the
  scenario explains, before they run it, that it is permanent.
- **It is real, and it says so.** The adapter, the scenario and the contract
  are tested offline; the live run is the one thing left, and it needs only
  a funded key and faucet MON. Nothing in the repo pretends a live run
  happened.

## Before the event

- [ ] Fund a key from https://faucet.monad.xyz
- [ ] Replace `alice` in `scenarios/first-monad-transfer/scenario.toml` with
      the key's address; set `bob` to a fresh address
- [ ] Deploy `GenesisLedger` (`contracts/README.md`) and set
      `GENESIS_MONAD_LEDGER`
- [ ] Do one live scenario run and one live anchor; keep the explorer links
- [ ] Rehearse the 60-second demo above, in order, with the terminal visible

## What not to claim

- Never claim a live Monad run, a deployed contract address, or a transaction
  hash you have not actually produced. The repo is explicit about this, and
  the judges can check the explorer.
- Never claim the gas fee on Monad until a live run has measured it.
