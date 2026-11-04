# Nomi Island — playable Web3 learning prototype

The browser front door is now a scrolling, freely walkable 1600 × 1100 canvas
world. The player controls Nomi; the native desktop pet is an optional launcher.
No account, wallet, model key or DSH installation is required.

The current presentation is a dusk pixel woodland: narrow paths, violet accents,
warm windows, trees with depth ordering, and a bottom dialogue stage with pixel
speaker portraits. [Official design references and scope](PIXEL_ART_DIRECTION.md).

## Play

```powershell
Set-Location D:\Github\project-genesis
.\scripts\Setup-Genesis.ps1
.\scripts\Start-Genesis.ps1
```

Open the printed URL, normally `http://127.0.0.1:8000/`. If updating an existing
checkout, rebuild and refresh the browser; restart for backend changes.

- WASD or arrows: move. Diagonal speed is normalized. Buildings and pond block movement.
- Hold Shift: run. Click open ground: walk toward that spot. Clicking does not pathfind around buildings; use the keyboard to steer around obstacles.
- E near a building/terminal: talk or inspect. Esc closes the dialogue or opens the pause menu.
- During dialogue, E / Enter or the next-line button advances the conversation. Actions remain accessible without waiting through every line.
- M: toggle the map. It is hidden during ordinary exploration and dialogue.
- Space: pick up a nearby practice parcel, throw it if carrying, or hop. Put it in Bob's delivery circle for an optional toy objective. Walking over three purple signals collects them.
- Small screens: hold the direction buttons; use the nearby-interaction and parcel buttons. Pointer release/cancel and window blur clear movement.

Walk northwest to Alice, accept her commission and read the original approval.
Walk northeast to the relay and read the incoming request. At the southern
payment terminal choose a rule and run both requests. A weak rule can pay the
wrong account. Rewind and try again; the exact intent matching rule pays the
authorized request and refuses the inconsistent one. Scores, receipts, account
balances and reset verification come from the backend. A refused request has
no receipt; a failed mined receipt is shown separately.

Optional stops: Bob's studio compares the documents; the other warehouse shows
live accounts on entry; the workshop opens the Solidity exercise and optional
official Remix editor. The evidence book keeps inspected snapshots; use the
judge's per-experiment balances for transaction outcomes. No successful
transaction is inferred from carrying a toy parcel.

## Implementation boundary

`frontend/src/world/engine.ts` handles presentation movement, collision, camera
targets, carrying, jumps and exploration collectibles. `render.ts` draws the
world and visualizes actual returned transaction destinations. These are not
part of the deterministic Python economy or blockchain judge. Frame timing
affects toy motion; it never affects security grades or chain balances.

`art.tsx` holds original character grids shared by world sprites and dialogue
portraits. `landscape.ts` defines fixed trails and tree positions; trunks are
included in collision. The renderer caches static terrain/building/tree art,
sorts objects by their foot point, and scales a low-resolution buffer with
smoothing disabled. Reduced motion freezes environmental animation; movement
and input remain available. This visual noise function is separate from the
Python engine's seeded RNG.

`WorldGame.tsx` connects nearby interactions to the existing `useLab` hook.
The hook is the only API caller. Its `experiment` action runs choice then
replay inside one busy lock/error boundary: a rejected choice cannot fall
through to replay. Existing idempotency keys, stale-version handling and
server-side permissions remain in force. Walking/exploration issue no POSTs.

Dialogue pauses movement, traps keyboard focus and returns focus to the
canvas on close. Backend failure leaves exploration available and shows a
reconnect action. Keyboard movement is ignored while typing or using menus.
The frontend keeps the toy world while navigating to/from the workshop.
`checkpoint.ts` saves location, toy parcel, collected signals and delivery state
every two seconds, on page hide and on leaving the world, using the versioned
localStorage key `genesis.island.exploration.v1`. Invalid coordinates, unknown
versions and malformed saves fall back to safe defaults. Blocked storage leaves
exploration playable and displays a note in the menu. This is local toy progress;
no permissions, balances, receipts or grades are stored there. The backend session resumes while
the same lab process remains alive. A server restart loses that in-memory
session, as before.

The previous companion dashboard remains at `/#space`, its direct mission
panel at `/#mission`, and the historic pixel investigation at `/#town`.
They share the authoritative mission service. These are secondary views,
available from the menu rather than additional steps in the main game.

## Current limits and next milestone

This is a single-player interaction prototype with one mission, code-authored
pixel art and basic local toys. The optional native pet still uses an earlier
illustrated asset; it is a secondary prototype. There are no
interiors, generated dialogue, multiplayer,
combat or production game animation. Canvas scenery is not a full screen-reader
game; the menu's text mission panel is available as an alternative.

All chain execution is local Anvil. No tested Monad Testnet or DSH connection
is present. The mobile layout is available; no real iPhone/Safari verification
is claimed. Remix remains an optional desktop-oriented external service.

Next: playtest movement and mission clarity with users, improve bespoke map
art/animation, add a second purposeful world interaction, then separately
implement and verify a Monad Testnet graduation challenge. Expand the world
only when its activities give the player something useful to do.
