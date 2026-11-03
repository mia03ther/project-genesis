# First Local Blockchain Transfer

**Level:** beginner · **Time:** about 15 minutes · **Network:** a private
Anvil chain on your own computer (nothing here touches a public network)

## What you will learn

- What an account balance is, and how wei relates to ether
  (1 ether = 1,000,000,000,000,000,000 wei)
- How a plain value transfer moves ether from one account to another
- How to read a transaction receipt: status, gas used, effective gas price
- Why the sender pays the value **plus** a gas fee, while the recipient
  receives exactly the value
- What a nonce is, and why it rises by one with every transaction

## The setup

| Account | Address | Starts with |
| --- | --- | --- |
| alice | `0x00000000000000000000000000000000000a11ce` | 10 ether |
| bob | `0x0000000000000000000000000000000000000b0b` | 0 ether |

Both accounts are synthetic: they have no private keys, and the ether exists
only on a throwaway local chain. The harness asks the chain to accept
transactions from them on their behalf (Anvil calls this *impersonation*).

**Task:** send 1.5 ether from alice to bob.

## Run it

From the repository root, with Foundry installed (see the main README) and
`anvil` on `PATH`:

```powershell
$env:Path = "$env:USERPROFILE\.foundry\bin;$env:Path"
```

```powershell
.\.venv\Scripts\python.exe main.py scenario run first-local-transfer
```

The harness starts a private chain, gives alice and bob their starting
balances, sends the transfer, checks the result against eight criteria, writes
`reports\first-local-transfer.json`, and restores the starting state.

Try a mistake and see what the judge says:

```powershell
.\.venv\Scripts\python.exe main.py scenario run first-local-transfer --value "1 ether"
```

## What the checks mean

| Criterion | Why it matters |
| --- | --- |
| transaction-succeeded | A receipt with status 1 means the transfer was executed. |
| sent-by-alice, sent-to-bob | The transaction's `from` and `to` are the right accounts. |
| exact-value | The value is exactly 1,500,000,000,000,000,000 wei. |
| bob-received-the-value | The recipient pays no gas, so bob ends with exactly 1.5 ether. |
| alice-paid-value-and-fee | Alice pays 1.5 ether plus gas used x effective gas price, to the wei. |
| plain-transfer-gas | A plain transfer to an account without code uses 21,000 gas. |
| alice-nonce-increased | Each transaction from an account raises its nonce by one. |

## Why hashes are not compared

A transaction hash covers fields chosen by the node, such as the gas price,
and a block hash also covers the block's timestamp. They are therefore not
guaranteed to be the same between runs, machines or Anvil versions. The report
records them under `environment_specific` and compares only what the scenario
fixes: who sent what to whom, and how every balance and nonce changed.
