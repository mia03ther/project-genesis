# GENESIS independent desktop companion

The current browser product is [Nomi Island](NOMI_ISLAND.md): a controllable pixel game with an optional native desktop companion. The game has an original pixel interpretation of Nomi; this native window retains its earlier illustrated asset. The native window is a Windows/Tk prototype; it does not require DeepSeek Harness, model API keys, or a wallet. Its mission button opens the game. The old companion dashboard is at /#space and the pixel town is archived at /#town. The Solidity workshop is an optional next step, not an assessment of user-authored code.

## Run for review

Prerequisites: Windows, Python 3.12 with Tk (the verified uv Python includes it), uv, current Node.js LTS, and Foundry/Anvil. Foundry Windows releases: https://github.com/foundry-rs/foundry/releases. Extract the official Windows archive into `%USERPROFILE%\.foundry\bin` or put `anvil.exe` on PATH.

```powershell
git clone https://github.com/mia03ther/project-genesis.git
cd project-genesis
git switch feat/genesis-security-lab-v0.2
.\scripts\Setup-Genesis.ps1
.\scripts\Start-Genesis.ps1 -WithPet
```

The setup script installs Python dependencies and builds the UI from the committed npm lockfile. It does not install Foundry or modify your shell/profile/execution policy. If your PowerShell policy blocks scripts, run these equivalent commands individually:

```powershell
uv venv --python 3.12 .venv
uv pip install --python .venv\Scripts\python.exe -e '.[lab,dev]'
npm --prefix frontend ci
npm --prefix frontend run build
.\.venv\Scripts\python.exe -m genesis.launch --pet --anvil "$env:USERPROFILE\.foundry\bin\anvil.exe"
```

An existing environment can be reused; do not recreate it unnecessarily. No account signup is required for the local demo. Remix is an external website and needs internet access when opened.

`Start-Genesis.ps1 -Port 8011 -WithPet` avoids an occupied port. The launcher reuses a healthy GENESIS lab if already present, otherwise starts its own loopback server and Anvil. With `-WithPet`, closing its pet gracefully stops the server it owns. Without it, the browser game opens directly and Ctrl+C in the terminal stops its service. It does not stop a pre-existing lab. `-NoBrowser` only prints the URL. Access the browser mission at the printed localhost URL and the workshop at `/#workshop`.

For the pet alone (it stays usable while the lab is offline):

```powershell
.\.venv\Scripts\python.exe -m genesis.pet
.\.venv\Scripts\python.exe -m genesis.pet --framed  # title bar/accessibility diagnostic mode
```

## Interactions and truthful state

- Drag the character to move it on the primary display. A click pets it; the toolbar provides feeding, petting, the mission, the workshop and exit. Right-click for rest or quiet mode. Escape exits.
- Feeding shows a bowl and a bounce; petting shows a sparkle; resting adds a sleep cue. These are local deterministic presentation interactions, not LLM replies or learning credit.
- A background worker reads only `/api/health` and `/api/session` from `http://127.0.0.1:<port>`, bypassing proxies and refusing redirects. It never POSTs or signs transactions.
- The current mission/result drives investigating, ready, success or retry expressions. A disconnected backend explicitly shows offline; it never invents a successful experiment.
- Feeding/petting counts persist locally at `%LOCALAPPDATA%\GENESIS\companion.json`. No model keys, wallet keys or chain grades are stored there. Corrupt local files fall back to a clean pet state.

This is an initial animation prototype: one generated character with bob/bounce/effect animation, not a large hand-animated sprite library. Primary-display movement is implemented; multi-monitor placement, click-through, system tray and executable packaging are future work. The Tk colorkey transparency can differ across Windows display settings; `--framed` is available for troubleshooting. No native iPhone desktop-overlay support is claimed.

## DSH and Monad status

DeepSeek officially documents its Harness plugin architecture at https://www.deepseek.com/harness/en/ and https://github.com/deepseek-ai/deepseek-harness. GENESIS currently has **no tested DSH plugin or live DSH event connection**. A future optional adapter should translate documented host task states into companion presentation, with an explicit opt-in and no model/credential copying. The independent local demo remains the default.

The purple artwork evokes collectible digital art; there is no NFT, token issuance, blockchain ownership, or Monad endorsement. All current mission execution is local Anvil. Monad Testnet will require its own adapter, test-funded accounts and actual network tests; it has not been integrated.

## Artwork provenance

`genesis/pet/assets/companion.png` is an original built-in image generation output, copied into this repository. It does not reuse DSH Big Fat Fish artwork. The final asset depicts a matte lavender pebble-shaped designer toy, a dark visor with small ivory eyes, floppy violet ears, tiny limbs and a purple belly button, on transparent background. Earlier exploratory fish/manta artwork is not used. The desktop and web import the same final PNG and identity.json palette.

## Next practical milestone

Test the character and interaction feel with actual users before expanding the world. Then add a documented DSH task-state adapter, richer character animation, and one separately verified Monad Testnet graduation challenge. The current architecture must not be described as an autonomous wallet protector or production security product.
