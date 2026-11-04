# GENESIS pixel adventure — design notes, 2026-11-04

The player asked for a more considered single-player game, pixel art, and a
Galgame-style dialogue box at the bottom. This implementation keeps the existing
mission engine and replaces the browser world's visual presentation.

## Official references read

- [Apple Design Awards 2023: Afterplace](https://developer.apple.com/design/awards/2023/) and [Apple's developer interview](https://developer.apple.com/news/?id=3exkgv43): exploration, readable characters and a small control vocabulary. We borrow the principle of entering play immediately and finding guidance inside the world. This is an Apple Design Award, not an App Store Game of the Year claim.
- [Apple Design Awards 2025](https://developer.apple.com/design/awards/2025/): Balatro demonstrates focus around a clear core mechanic; Neva connects scene palette, camera and emotional tone. For GENESIS this means one understandable payment commission and a coherent dusk palette. It does not mean adding card combat or imitating their characters.
- [Steam Awards 2019](https://store.steampowered.com/steamawards/2019/) identifies GRIS as Outstanding Visual Style winner. [The publisher's game page](https://www.devolverdigital.com/games/gris) describes its art-led journey. Our interpretation: quieter UI, clear silhouettes, controlled color, and space for the world to be seen.
- [Sea of Stars official game site](https://seaofstarsgame.co/): a separate pixel-art reference for layered scenery, expressive traversal and environmental light. It is not being described here as a Steam Awards winner. GENESIS uses inexpensive drawn lighting accents, not that game's lighting technology.

These are official-page and developer-description references, not a claim to
have played or comprehensively evaluated the games. Commercial artwork, music,
fonts, dialogue and game maps were not imported into this repository.

## Decisions implemented

The world uses muted blue-green terrain, ink shadows, lavender roofs/waymarkers,
and amber windows. Monad purple remains an accent. Woodland trails replace broad
rectangular streets. Grass texture, roof tiles, stonework, reeds and foliage are
drawn on a low-resolution buffer. Static artwork is cached; objects share a depth
order. Tree trunks participate in collision, with clear approaches to residents.
A flood-fill test checks that every interaction remains reachable from spawn.

Nomi and residents are original pixel grids. The same grids supply the dialogue
portraits. The browser world no longer places a smooth illustrated pet over a
different art style. The optional native Tk pet retains its previous illustration
and is outside the new browser art pass.

Dialogue docks across the bottom. A speaker portrait and name anchor the text;
the environment remains visible above it. Receiving a document shows a compact
address/amount slip. Full documents and the evidence book expand on request.
Transaction rules and results stay in the same dialogue stage. Closing returns
keyboard focus to movement. The map is optional via M or its button.

The ordinary controls remain WASD/arrows, Shift, E, Space and Esc. There are no
new model calls, network destinations, grading rules or wallet capabilities.

## Verification and limits

See [executed checks](validation/PIXEL_CHECKS.md). Unit tests exercise actual
API-shaped investigation/replay/reset, focus recovery, movement, map toggle and
forest reachability. TypeScript's strict configuration and the production build
are checked. An offline raster preview executes the actual Canvas drawing code;
it does not validate browser CSS layout or substitute for Safari testing.

The desktop/browser automation service timed out waiting for application
approval during this pass, so final browser visual verification is not claimed.
Real iPhone verification remains outstanding. This is still a small original
prototype, not a claim to match the production art or content volume of the
reference games. No combat, interiors, soundtrack or new missions were added.
