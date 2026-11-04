# Solidity workshop and Remix

From the game menu choose **合约工坊**, visit its island building, or open `http://127.0.0.1:8000/#workshop` after building the frontend. The workshop is accessible before a case is completed. Returning resumes the backend session and local island exploration.

The opening activity is a rule-crafting board: select recipient, amount and network seals, then test four fixed teaching samples. Incorrect choices show which sample was accepted/rejected; changing a seal clears the old result. All four samples must be handled correctly to generate a Solidity exercise draft. This is a deterministic preview of the selected rules, **not execution or grading of the edited Solidity**. It sends no API requests and awards no chain grade. Replacing an edited draft requires a second confirmation; changing the configuration cancels pending replacement. The workshop shares the island's pixel portrait, ink/lavender palette and return-to-island entry.

The first exercise converts the Wrong Recipient lesson into a pure Solidity predicate. The starter deliberately omits the recipient comparison; it has a warning and no transfers, deposits, external calls, or actual authorization signatures. A reference implementation checks recipient, value, and the supplied chain ID. This is not a production wallet guard: supplying a chain ID is not proof of the active network, and payer authentication is outside this lesson.

The browser editor stores a local draft, copies/downloads `.sol`, and opens the official Remix IDE with UTF-8 base64 source in the URL fragment. Restoring the starter requires confirmation. The current source size limit is 24 KB. Embedded Remix connects only after an explicit click, in a sandboxed cross-origin iframe; a new-window link is always provided as fallback. The parent CSP permits only official Remix origins as frame destinations. There is no arbitrary RPC endpoint or server-side user-code compilation API.

Official references checked on 2026-11-03:

- https://remix-ide.readthedocs.io/en/latest/locations.html documents `code`, `embed`, `theme`, `activate` and compiler-version parameters. It warns that generated code-sample workspaces are ephemeral: rename/export them before reloading.
- https://remix-ide.readthedocs.io/en/latest/index.html identifies `https://app.remix.live` as the current official site, and explicitly says tablets and phones are unsupported.

The URL pins Solidity 0.8.28 and opens the core Solidity/deployment plugins. Users must select **Remix VM**, not a wallet or public network. Third-party Remix may present its own consent dialogs and changes independently of GENESIS. No AI service is required by the lesson. Changes within Remix are not synced back to the GENESIS draft.

Four manual vectors are supplied: Bob/value/chain all correct -> true; similar wrong address -> false; wrong amount -> false; wrong chain -> false. These expectations are not presented as results for the user's code. GENESIS cannot inspect the cross-origin editor's code or grades, and does not award completion merely for opening it.

Reference tests run without third-party Solidity libraries:

```powershell
cd contracts\authorization
& "$env:USERPROFILE\.foundry\bin\forge.exe" test -vv
```

The six tests cover those vectors, show that the incomplete starter accepts the wrong address, and fuzz rejection of other recipients (256 runs). Foundry compiles repository-owned files only. The first run may download the pinned official Solidity compiler. Arbitrary uploaded Solidity must not later be executed without a separately designed resource/isolation boundary.

Browser verification: embedded Remix loaded and displayed the exercise source. Its AI/analytics consent prompt appeared; no consent was accepted and no in-browser compilation/deployment was claimed. Compilation and behavioral verification were performed separately using local Foundry. iPhone Safari and remote access are not verified.

Developer check of the current **generated** Solidity (Node 24, Foundry and cached solc 0.8.28):

```powershell
node scripts/Check-Workshop.cjs --forge "$env:USERPROFILE\.foundry\bin\forge.exe"
```

This writes a temporary project under `reports/crafted-check`, compiles it offline,
runs four behavioral tests and writes `report.json`. It never reads the browser's
edited draft. If the compiler is not cached, first run the reference Foundry
suite above with internet access to acquire the official pinned compiler.
