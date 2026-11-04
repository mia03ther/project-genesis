# GENESIS / Nomi — Blitz prototype

## One controllable game, optional companion

The browser front door is Nomi Island: a controllable character, free movement, nearby interactions, a practice parcel and optional exploration signals. WASD/arrows move, Shift runs, E interacts, Space picks up/throws/hops. The native desktop companion opens this same game. The mission journey is: meet Alice, read her approval, collect the relay's request, try a rule at the payment terminal, observe actual local-chain results, rewind, then optionally express the rule in Solidity with Remix.

The earlier pixel town remains at `/#town` for comparison and regression. The previous companion dashboard is at `/#space`; its direct mission panel remains at `/#mission`. These are secondary alternatives. The island uses nearby locations, a small objective HUD and one dialogue at a time. The backend still requires reading authorization and request evidence before selecting a strategy. Toy movement and collecting never change grades. See [controls and limits](NOMI_ISLAND.md).

## Visual research and decisions (2026-11-03)

Sources inspected: https://monad.xyz/ and its linked https://monad.xyz/brand-and-media-kit. The published inline styles contain `--color-brand-purple-primary: #6e54ff`, lavender `#b8b4fe`, off-black `#0e100f`, and off-white `#fbfaf9`. The site declares Britti Sans and Inter. GENESIS uses system sans-serif fallbacks; it does not copy/rehost the site's font binaries, logos or illustration assets. Browser navigation to the official site timed out; the color/font findings were read from the site's published HTML/CSS, not from a claimed completed visual browser tour.

The November 4 [pixel art pass](PIXEL_ART_DIRECTION.md) supersedes the earlier off-white browser map. The browser now uses a dusk woodland, code-authored pixel sprites/portraits, amber windows, muted lavender accents and a bottom dialogue stage. The optional native desktop pet and archived companion dashboard retain the earlier illustrated PNG. These are secondary prototypes; they should not be presented as a completed unified production art set.

Feeding/petting produce presentation reactions, never chain credits or grade changes. Mission status is read from the same authoritative Python service. The web and native pet do not synchronize local touch/feeding counters; shared progress means the actual mission/session state, not a claimed distributed pet database.

## Honest hackathon scope

- Runs independently; no DSH install, model key or wallet is needed for the local reviewer demo.
- DSH plugin/event integration is not implemented or tested. Official reference: https://www.deepseek.com/harness/en/ and https://github.com/deepseek-ai/deepseek-harness.
- Monad-inspired visuals and a prospective Blitz demo are not Monad Testnet integration. Execution currently uses Anvil only.
- The Solidity reference contract is tested locally. User-written Remix code is not automatically graded or sent to the local server.
- The companion is a Tk animation prototype, not a fully animated production pet or an autonomous wallet protector.

## Two-minute reviewer journey

1. Open the browser game. Move, run, pick up and throw the practice parcel (15 seconds).
2. Walk to Alice and the relay; E opens each interaction. Compare full recipient addresses (30 seconds).
3. At the payment terminal, try a weak rule and run both requests with one action. Show the backend-derived recipient, receipt and changed balances (30 seconds).
4. Rewind, choose exact intent matching and replay. The correct request is paid; the inconsistent one has no submitted transaction (30 seconds).
5. Close the dialogue to see returned transaction routes, then visit the optional contract workshop (15 seconds). Local Foundry tests verify the reference; user-code grading is future work.

For reproducible review use README setup and `scripts/Start-Genesis.ps1`. Do not describe the current build as production multi-user, live DSH-connected, deployed on Monad, iOS-native or proven to improve learning. Those require separate implementation and evidence.

## PowerShell startup troubleshooting

`ModuleNotFoundError: genesis` from a prompt showing `~` usually means a home-directory virtual environment was used. Run:

```powershell
Set-Location D:\Github\project-genesis
.\.venv\Scripts\python.exe -m genesis.lab --anvil "$env:USERPROFILE\.foundry\bin\anvil.exe"
```

Or invoke `& 'D:\Github\project-genesis\scripts\Start-Genesis.ps1'` from any directory. The script resolves the checkout and Python path itself. The unrelated PowerShell profile alias error `AliasAllScopeOptionCannotBeRemoved` is resolved by preserving `-Option AllScope` when replacing the built-in `gp` alias. Changes to a personal profile are local and are not distributed with GENESIS.
