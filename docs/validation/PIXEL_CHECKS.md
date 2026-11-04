# Pixel adventure validation — 2026-11-04

Commands executed from `D:\Github\project-genesis` on Windows, using the existing
Python 3.12 virtual environment and installed frontend dependencies:

```powershell
npm --prefix frontend test
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m mypy genesis --strict
.\.venv\Scripts\python.exe -m ruff check genesis tests main.py --select E,F,W,B,I,UP,SIM,RUF --line-length 130
git diff --check
```

Observed results:

- Vitest: **6 files, 31 tests passed**, 42.82 seconds. Includes forest reachability, keyboard/touch movement, pause/focus, optional map, document expansion, failed payment strategy, rewind, passing strategy and rejection without unintended replay.
- Production build: TypeScript strict checking passed; Vite built 41 modules. Final JS asset approximately 332.43 kB before gzip, 106.95 kB gzipped. The previous companion illustration remains in the optional dashboard bundle's assets.
- mypy: **32 source files, no issues**.
- Ruff: **all selected checks passed**.
- `git diff --check`: no whitespace errors; Windows Git emitted ordinary LF/CRLF conversion notices.

The source used by the renderer was also executed through a temporary offline
Canvas raster adapter. Its two 1280 × 720 output images are in
`docs/screenshots/pixel-*-render.png`. They were visually inspected and the
terrain contrast was reduced after inspection. These images contain scenery
only: they are **not browser screenshots**, do not exercise CSS, and do not
prove final dialogue layout or performance in a browser.

Browser automation was attempted, but the desktop app authorization timed out.
No completed browser visual check or real iPhone/Safari check is claimed for
this art pass. The game remains available from the local server; refresh after
building to load the new frontend.

The preceding backend verification on November 3 completed **658 pytest tests**,
including actual local Anvil and opted-in Tk checks, plus **6 Foundry tests**
(including 256 fuzz runs). The reference scenario report in
`wrong-recipient-anvil.json` records four successful runs with matching
normalized digests and verified resets. Those results are historical evidence,
not a claim that the Python/Foundry suites were rerun during this frontend-only
art pass. No core simulator or chain-grading code changed in this pass.
