# First Monad Transfer

Send 1.5 MON from one account to another on **Monad Testnet** (chain 10143),
then read the receipt and confirm exactly what changed.

This is the same transfer as `first-local-transfer`, on a public chain
instead of a local one. The differences are the lesson:

| | Anvil (local) | Monad Testnet (this scenario) |
| --- | --- | --- |
| Accounts | synthetic, impersonated, no keys | a real funded key signs the transaction |
| Funds | set directly on the local chain | free test MON from the faucet |
| Reset | snapshot / revert after every run | **impossible** — history is permanent and public |
| Repeat | `--repeat N` checks identical runs | refused: every run starts from different balances |

## Run it offline first (no key, no network)

Against a loopback test double the scenario runs unsigned, exactly like the
Anvil one. The test suite does this (`tests/test_harness_monad.py`); from a
shell, point it at a local Anvil node started for Monad's chain id:

```bash
anvil --chain-id 10143 --port 8545 &
python main.py scenario run first-monad-transfer --rpc-url http://127.0.0.1:8545
```

## Run it live (real transaction, costs test MON)

1. Fund a key: get free test MON from https://faucet.monad.xyz.
2. Replace the `alice` address in `scenario.toml` with your key's address,
   and set `bob` to a fresh address (zero balance).
3. Run it — one run only, it cannot be repeated or undone:

```bash
export GENESIS_MONAD_PRIVATE_KEY=0x...
python main.py scenario run first-monad-transfer
```

The report is written to `reports/first-monad-transfer.json` and prints the
explorer link for the transaction:
`https://testnet.monadexplorer.com/tx/<hash>`.

The key is never printed and never written to the report. If you pass it on
the command line instead (`--private-key`), it stays in your shell history —
the environment variable is the safer way.
