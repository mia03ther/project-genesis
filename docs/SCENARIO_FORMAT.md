# Scenario manifest format, version 1

A scenario is a directory under `scenarios/` containing `scenario.toml` (or
`scenario.json` with the same structure) and, optionally, a learner guide.
The loader ([genesis/harness/manifest.py](../genesis/harness/manifest.py)) is
strict: unknown fields are errors, so a typo never passes silently, and every
problem is reported at once with its location, e.g.
`accounts[1].address: '0x123' does not have the required form`.

Validate a manifest with:

```powershell
.\.venv\Scripts\python.exe main.py scenario validate scenarios\first-local-transfer
```

## Amounts

Every amount of ether is a **string** `"<number> <unit>"` with unit `wei`,
`gwei` or `ether`, for example `"1.5 ether"`, `"2.5 gwei"`, `"21000 wei"`.
Amounts are converted to integer wei exactly. Fractions of a wei, negative
amounts and amounts above 2^256 - 1 are rejected. Strings are used because
TOML integers stop at about 9.2 ether worth of wei, and floats are never exact.

## Fields

`manifest_version` (integer, required): `1`. Other versions are refused before
anything else is read.

### `[scenario]`

| Field | Type | Rules |
| --- | --- | --- |
| `id` | string, required | lower-case words joined by `-`, at most 64 characters; stable across versions |
| `version` | string, required | `MAJOR.MINOR.PATCH`; bump it whenever content or grading changes |
| `title` | string, required | shown to learners |
| `summary` | string, required | one or two sentences |
| `learning_objectives` | list of strings, required | at least one |
| `prerequisites` | list of strings | may be empty |
| `difficulty` | string, required | `beginner`, `intermediate` or `advanced` |
| `estimated_minutes` | integer, required | 1 to 600 |
| `tags` | list of strings | lower-case words joined by `-` |

### `[environment]`

| Field | Type | Rules |
| --- | --- | --- |
| `kind` | string, required | only `anvil` (a local development chain) in version 1 |
| `chain_id` | integer, required | the chain must report this id; `31337` is Anvil's default |

### `[[accounts]]` (2 to 16)

| Field | Type | Rules |
| --- | --- | --- |
| `label` | string, required | unique; lower-case words joined by `-` |
| `address` | string, required | `0x` + 40 hex digits, unique, stored lower-case; addresses up to `0x…03ff` are refused because precompiles and system contracts live there |
| `balance` | amount, required | the exact starting balance |
| `description` | string | for learners |

Accounts are synthetic: they have no private keys, and the harness has Anvil
impersonate them. Every account must start with nonce 0 and no code; the
environment verifies this after initialization and after every reset.

### `[transaction]`: the expected transaction

| Field | Type | Rules |
| --- | --- | --- |
| `from` | string, required | an account label |
| `to` | string, required | another account label |
| `value` | amount, required | the sender's starting balance must exceed it, to leave room for gas |
| `gas_limit` | integer | 21,000 to 30,000,000; default 21,000 |

### `[grading]` and `[[grading.criteria]]` (1 to 32)

`pass_threshold` (integer) is the minimum score; it defaults to the maximum,
so every point is needed. A run passes when it reaches the threshold **and**
no criterion marked `required` failed.

| Criterion field | Type | Rules |
| --- | --- | --- |
| `id` | string, required | unique; lower-case words joined by `-` |
| `check` | string, required | one of the checks below |
| `description` | string, required | what the learner should understand |
| `points` | integer | 0 to 100; default 1 |
| `required` | boolean | default `false` |
| `account` | string | an account label, for checks that use it |
| `expect` | depends on the check | see below |

| Check | `account` | `expect` | Passes when |
| --- | --- | --- | --- |
| `receipt_status` | no | `"success"` (default) or `"reverted"` | the receipt status is 1 or 0 respectively |
| `sender` | no | no | the transaction came from the address of `transaction.from` |
| `recipient` | no | no | the transaction went to the address of `transaction.to` |
| `value` | no | no | the transaction carried exactly `transaction.value` |
| `final_balance` | required | amount, required | the account's balance after the run equals `expect` |
| `sender_pays_value_and_fee` | no | no | the sender's balance fell by exactly value + gas used x effective gas price |
| `gas_used` | no | integer, required | the receipt's gas used equals `expect` |
| `nonce_increment` | optional (default: the sender) | integer (default 1) | the account's nonce rose by `expect` |

A field a check does not use is an error. Defaults are written into the parsed
manifest, so the manifest digest reflects them.

### `[metadata]`

Optional: `authors` (list of strings), `created` and `updated` (dates such as
`2026-11-02`), `license`, `notes` (strings) and `networks` (list of strings,
for example `["anvil-local"]`).

## Identity and versioning

- `ScenarioManifest.digest()` is the SHA-256 of the canonical JSON form of the
  parsed manifest. TOML and JSON spellings of the same content, comments and
  formatting do not change it; any change to content or defaults does. Reports
  record it, so a result always names the exact scenario it was graded against.
- `scenario.version` is the author's version of one scenario.
- `manifest_version` is the version of this format. A build reads only the
  versions it knows; new task kinds (contract calls, other networks) will come
  with a new format version rather than reinterpreting version 1.

## The report: `genesis.scenario-report`, version 1

`genesis scenario run` writes a JSON report (default `reports/<id>.json`). It
contains no timestamps, so everything outside `environment` and the
`environment_specific` sections is reproducible. A real example, produced on
Anvil 1.8.7, is [examples/first-local-transfer.report.json](examples/first-local-transfer.report.json).

| Field | Meaning |
| --- | --- |
| `report_format`, `report_version`, `genesis_version` | what wrote the report |
| `status` | `passed`, `failed` (graded below the threshold or a required criterion failed), `rejected` (the submission was refused, so nothing was graded) or `error` (the environment failed, e.g. Anvil is missing) |
| `error` | the error message when `status` is `error` |
| `scenario` | id, version, title, manifest version, manifest digest and source path |
| `actor` | who made the submission, e.g. `reference` |
| `environment` | node kind, client version, chain id and RPC URL; whether the harness started the node itself |
| `summary` | runs, passed runs, score, maximum score, pass threshold |
| `runs[]` | per run: status, submission, rejection reasons, grading (each criterion with expected and actual values), observation, normalized digest, and whether the reset was verified |
| `runs[].observation.normalized` | chain id, sender, recipient, value, status, gas used, balances before, balance changes with the fee added back for the payer, nonce changes |
| `runs[].observation.environment_specific` | transaction hash, block hash, block number, effective gas price, fee, transaction type, client version |
| `reproducibility` | the normalized digests of all runs, whether they agree, the list of environment-specific fields, and a note on normalization |

The normalized digest covers the normalized observation plus which criteria
passed and the score, nothing that depends on the node. Two runs of the same
scenario from the same initial state must produce the same digest. Transaction
and block hashes are not compared, and matching hashes are not claimed, not even
between runs on one machine.
