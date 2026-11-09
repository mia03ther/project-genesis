# GenesisLedger — the on-chain anchor for Project GENESIS

`GenesisLedger.sol` records a simulated world's state digest on Monad
Testnet, so anyone can check that a world they re-run locally matches the
world that was anchored. The simulation stays deterministic and off-chain;
the chain is only the proof.

## What it stores

`recordWorldDigest(day, digest, population, trades)` stores one snapshot per
day and emits a `WorldAnchored` event. A later anchor for the same day
overwrites the earlier one; the full history is in the events.
`getDigest(day)` returns the digest for a day (zero when nothing was
anchored). The contract moves no money and is not a token.

## Build

```bash
cd contracts
forge build
```

## Deploy to Monad Testnet

You need a funded key: get free test MON from the faucet at
https://faucet.monad.xyz, then set it (never commit it):

```bash
export GENESIS_MONAD_PRIVATE_KEY=0x...
forge create --rpc-url https://testnet-rpc.monad.xyz \
  --private-key "$GENESIS_MONAD_PRIVATE_KEY" \
  GenesisLedger.sol:GenesisLedger
```

Note the deployed address, then tell the CLI about it:

```bash
export GENESIS_MONAD_LEDGER=0x<deployed address>
```

## Anchor a world

Run the demo, take its state digest, and anchor it:

```bash
python main.py demo            # note the "State digest" line
python main.py monad anchor --digest 0x<digest> --day 100 --population 20 --trades 3867
```

The command prints the transaction hash and its explorer link
(`https://testnet.monadexplorer.com/tx/<hash>`). Anyone can then verify it:

```bash
cast call <contract> "getDigest(uint256)(bytes32)" 100 --rpc-url https://testnet-rpc.monad.xyz
```

## Status

The contract compiles with Foundry 1.9.0. It has **not** been deployed to
Monad Testnet yet — deployment needs a funded key, which this repository
does not contain.
