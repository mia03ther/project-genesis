"""Opt-in native widget integration; regular headless tests do not require a display."""
import os
from pathlib import Path

import pytest

pytestmark = pytest.mark.desktop


@pytest.mark.skipif(os.environ.get("GENESIS_DESKTOP_TESTS") != "1", reason="set GENESIS_DESKTOP_TESTS=1 on a desktop with Tk")
def test_native_toolbar_asset_and_persistence(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    tk = pytest.importorskip("tkinter")
    from genesis.pet.__main__ import Companion
    from genesis.pet.state import PetState

    # The native widgets are real; backend networking is tested independently.
    monkeypatch.setattr(Companion, "poll", lambda self: None)
    root = tk.Tk()
    root.withdraw()
    try:
        state = tmp_path / "pet.json"
        companion = Companion(root, "http://127.0.0.1:8000", state)
        assert companion.sprite is not None and companion.sprite.width() > 0
        buttons = {str(button.cget("text")): button for button in companion.controls.winfo_children()}
        buttons["喂食"].invoke()
        assert companion.mood == "eat"
        buttons["摸摸"].invoke()
        assert companion.mood == "loved"
        assert PetState.load(state) == PetState(meals=1, cuddles=1)
        companion.interact("sleep")
        assert companion.sleeping is True
        buttons["摸摸"].invoke()
        assert companion.sleeping is False
        root.update_idletasks()
    finally:
        root.destroy()
