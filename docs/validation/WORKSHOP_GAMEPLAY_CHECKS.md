# Workshop gameplay validation — 2026-11-04

This increment adds the three-seal workshop trial, generated lesson code with
draft replacement protection, E/Enter dialogue beats, and local exploration
checkpoints. Python simulation, API actions and chain grading are unchanged.

Executed from the repository root:

```powershell
npm --prefix frontend test
npm --prefix frontend run build
node scripts/Check-Workshop.cjs --forge "$env:USERPROFILE\.foundry\bin\forge.exe"
git diff --check
```

- Frontend: **9 files, 40 tests passed**, 54.40 seconds. Includes all existing flows, every combination of the three seals, generated conditions, edited-draft confirmation, dialogue controls, invalid/blocked checkpoint storage, and returning from the workshop at the restored location.
- Strict TypeScript and production build passed: 45 modules, JS 340.43 kB / 109.47 kB gzipped.
- Generated Solidity: compiled with **solc 0.8.28** and **4 Foundry tests passed** (valid request, wrong recipient, wrong amount, wrong chain). The permanent developer script repeated the checks using the compiler cache. [Machine-readable report](workshop-generated-code.json).
- Whitespace check passed, with ordinary Windows LF/CRLF notices.
- The stopped loopback preview was restarted on port 8015. Its health endpoint returned `ready`; the served index referenced the current `index-D3tXNgY6.js` build and that asset returned HTTP 200. This is an HTTP smoke check, not a browser visual test.

The first frontend run caught a keyboard event whose target was not an HTML
element. The handler now checks the target type before using `closest`; the
complete suite was rerun after the fix. Foundry's initial relative-root attempt
also failed on Windows; the developer script runs with an absolute project cwd.

The developer check only compiles repository-generated lesson code. Browser
edited Solidity is not executed or automatically graded. The four-sample board
previews only its selected field checks; results reset when a seal changes.
It does not award a chain grade. No new runtime dependencies or model calls were
introduced. `Check-Workshop.cjs` uses Node 24's built-in TypeScript stripping.

The browser automation interface reported that the in-app browser was unavailable,
so no new browser screenshot, browser visual pass or iPhone test is claimed.
Backend pytest was not rerun for this frontend increment; prior backend results
are recorded in [the earlier validation](PIXEL_CHECKS.md).
