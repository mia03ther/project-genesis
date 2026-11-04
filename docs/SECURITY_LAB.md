# Current product integration

The default browser entry is now the coordinated Nomi companion space. The earlier pixel game documented below remains at `/#town` for regression and comparison. See [PRODUCT_DIRECTION.md](PRODUCT_DIRECTION.md) and [COMPANION.md](COMPANION.md) for the current reviewer journey.

# Security Lab development

Phase 2 uses the existing mission state machine and Anvil harness. The React interface reads evidence, permissions, results and balances from FastAPI. One operation at a time is allowed in the UI; the API serializes access with its existing service lock. This MVP supports one process and one local user. Multiple tabs or users are not isolated. Loopback binding is not a hostile-code isolation boundary.

From the repository root in PowerShell:

```powershell
$env:Path = "$env:USERPROFILE\.foundry\bin;$env:Path"
uv pip install --python .venv\Scripts\python.exe -e ".[lab,dev]"
npm --prefix frontend ci
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m genesis.lab
```

Open http://127.0.0.1:8000. For development, run `npm --prefix frontend run dev` in another terminal and open http://127.0.0.1:5173. Vite proxies `/api` to port 8000.

Checks:
```powershell
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m pytest -m anvil
.\.venv\Scripts\python.exe -m mypy genesis --strict
npm --prefix frontend run typecheck
npm --prefix frontend test
npm --prefix frontend run build
```

Manual acceptance: open the case, inspect authorization and API request, compare complete addresses, inspect the remaining evidence, select a weak strategy, set it and run. Verify backend failure and the receipt and balance evidence. Reset, select complete-field validation, run again, and verify the legitimate payment is submitted while the inconsistent request has no transaction. Download the report. Reload, test recovery with the backend stopped, and repeat at mobile width. No visual verification is claimed until these steps are executed in a browser.

Two-minute demo: explain Alice's intent (20 seconds), inspect the similar address previews and full evidence (30 seconds), run the weak rule and show who actually received funds (30 seconds), reset and run complete validation (30 seconds), show the JSON report (10 seconds).

Future deployment: keep the Windows laptop as development workstation. The Ubuntu Server 24.04 i5-4590/16 GB node can host the Python service, static build and ephemeral Anvil processes. Campus Wi-Fi does not imply inbound reachability; use an authenticated SSH tunnel or private network. Monad needs a separate adapter, funding and tests. The next milestone is browser automation plus session revision/idempotency protection before supporting more than one browser client.

## Pixel investigation game (frontend, 2026-11-03)

The UI is a 2D pixel town, 「错付疑云 / The Wrong Recipient」, in Simplified Chinese. It is built with React, TypeScript, Vite and a hand-drawn SVG (`frontend/src/game/`) and uses no game engine. Tap a place and the detective walks there along the streets; dialogue, evidence cards and the objective update from the backend session.

Places: Alice's studio (authorized intent), the payment relay (API request), Bob's atelier (complete address check, 4 hex digits at a time), the chain archive (account ownership; reveals the ownerless warehouse), and the wallet terminal (transaction draft, the 5 strategy ids from `GET /api/mission`, run, rewind).

Rules the UI follows:

- Every stage, evidence item, balance, transaction and grade comes from an API response. Parcels only move after `POST /api/session/replay` returns. A parcel goes to Bob or the warehouse according to `transaction.to.label`, and stays at the terminal when no transaction was sent. Under `prefers-reduced-motion` the end state is shown directly.
- Only one action can be in flight. Buttons are disabled while busy and repeated taps are ignored. An epoch counter drops responses that belong to a case that was since restarted or rewound.
- Each action uses one `Idempotency-Key`. Network failures are retried with the same key. An HTTP error is never retried. After `Idempotency-Replayed: true` the client re-reads `GET /api/session` and does not adopt the cached `X-Lab-Version`. `stale-state` triggers a refresh.
- The raw JSON, transaction hashes, criteria explanations and the backend timeline live in the evidence book (证据册), not in the scene.

Development server with hot reload (backend must run on port 8000; Vite proxies `/api`):

```powershell
.\.venv\Scripts\python.exe -m genesis.lab --anvil "$env:USERPROFILE\.foundry\bin\anvil.exe"
npm --prefix frontend run dev
```

### Verification actually performed

Commands run, all passing:

- `npm --prefix frontend run typecheck`
- `npm --prefix frontend test`: 14 tests. `src/api.test.ts` covers the API client (3 tests). `src/App.test.tsx` has 11 interaction tests against a stateful fake backend built from fixtures captured from the real session logic.
- `npm --prefix frontend run build`

The interaction tests cover:

- loading;
- the title card;
- step-by-step evidence collection with Bob's atelier locked until both documents are found;
- stepping through the address and finding digit 36;
- the strategy POST body (`trust-api`, `exact-intent-match`);
- a failing run where funds reach `unknown`, then a rewind and a passing run;
- history in the evidence book, and closing it with Esc;
- double-tap protection, with exactly one request carrying `Idempotency-Key` and `X-Lab-Version`;
- a network retry reusing the same key;
- `Idempotency-Replayed`, which leads to `GET /api/session`, after which the old version is not reused;
- a `stale-state` refresh;
- a network error and reconnect;
- a 503 chain-unavailable error;
- resuming an existing session;
- hints;
- restarting from the evidence book.

Browser play-test: the built app was served by `python -m genesis.lab --port 8010` with real Anvil v1.8.7. It was played in the Claude desktop app's built-in Chromium browser pane.

- Desktop (1024×768):
  - collected all 5 pieces of evidence;
  - ran `trust-api`: both transfers were mined and `unknown` received 1.5 ETH;
  - rewound and ran `exact-intent-match`: Bob was paid and the spoofed request was refused with no transaction;
  - opened all three tabs of the evidence book;
  - reloaded mid-case: the session resumed;
  - keyboard: Tab to 开始调查, Enter, then focus moves into the dialogue.
- Emulated iPhone portrait (375×812 viewport, mobile user agent):
  - restarted the case from the evidence book (two-step confirm);
  - collected the evidence;
  - ran `refuse-all`: the legitimate request failed, 3/15;
  - rewound and ran `exact-intent-match`, then `preview-match`;
  - stopped the backend: a network error with recovery buttons was shown;
  - restarted the backend: the title card returned because sessions are in memory.

Problems found during play-testing and fixed:

- the side panel did not scroll on desktop (CSS specificity);
- the evidence book jumped in height between tabs;
- restarting did not walk the detective back to the studio;
- on a phone the result sheet covered the parcel animation;
- the HUD objective announced the result before playback finished;
- the focus ring had low contrast on cream panels;
- `viewport-fit=cover` was missing, so safe-area insets would have been ignored on iOS.

The only console errors left are the expected 404 from `GET /api/session` before a case exists (see `docs/FRONTEND_BACKEND_REQUESTS.md` item 4) and the connection errors caused by deliberately stopping the backend.

Screenshots from those sessions are in `docs/screenshots/` (`desktop-*.jpg`, `iphone-*.jpg`).

Not verified:

- no real iPhone or Safari/WebKit; only Chromium with a mobile viewport, so real safe-area insets and iOS tap behaviour are untested;
- no remote access (see `docs/IPHONE_PLAYTEST.md`; still not configured);
- the "重新连接" button click against a live restarted server (covered only by the unit test, because restarting the preview server reloaded the page);
- the JSON report download in a browser;
- a screen reader;
- `prefers-reduced-motion` in a real browser (covered by the tests, which run with reduced motion).

Files changed for the game:

- `frontend/index.html`
- `frontend/src/{App.tsx, App.test.tsx, api.ts, main.tsx, style.css}`
- `frontend/src/game/*`
- `frontend/src/test/{fakeBackend.ts, fixtures/*}`
- `docs/FRONTEND_BACKEND_REQUESTS.md`
- `docs/screenshots/*`
- `.claude/launch.json`: local preview config, port 8010.

No Python, scenario, grading or golden files were changed for the game.
