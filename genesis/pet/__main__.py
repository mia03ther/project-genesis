"""Native desktop companion: python -m genesis.pet (Python/Tk, no model keys)."""
from __future__ import annotations

import argparse
import json
import math
import os
import queue
import sys
import threading
import time
import tkinter as tk
import webbrowser
from contextlib import suppress
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from genesis.pet.identity import COLORS, NAME
from genesis.pet.state import PetState, local_endpoint, task_mood

BG = "#170d25"
INK = COLORS["ink"]
LILAC = COLORS["lavender"]


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str) -> None:
        return None


class Companion:
    """The worker only reads localhost; Tk and animation stay on the main thread."""

    def __init__(self, root: tk.Tk, endpoint: str, state_path: Path) -> None:
        self.root = root
        self.endpoint = endpoint
        self.state_path = state_path
        self.pet = PetState.load(state_path)
        self.stopping = threading.Event()
        self.updates: queue.Queue[tuple[str, str]] = queue.Queue(maxsize=1)
        self.mood, self.message = task_mood(None, False)
        self.task = self.mood, self.message
        self.until = 0.0
        self.sleeping = False
        self.quiet = False
        self.drag: tuple[int, int, int, int] | None = None
        self.dragged = False
        self.started = time.monotonic()
        root.title(f"GENESIS · {NAME}")
        root.geometry(f"320x350+{max(0, root.winfo_screenwidth()-360)}+{max(0, root.winfo_screenheight()-430)}")
        root.configure(bg=BG)
        root.attributes("-topmost", True)
        if sys.platform == "win32":
            root.overrideredirect(True)
            root.attributes("-transparentcolor", BG)
        root.protocol("WM_DELETE_WINDOW", self.close)
        root.bind("<Escape>", lambda _event: self.close())
        self.canvas = tk.Canvas(root, width=320, height=350, background=BG, highlightthickness=0)
        self.canvas.pack()
        self.canvas.bind("<ButtonPress-1>", self.press)
        self.canvas.bind("<B1-Motion>", self.move)
        self.canvas.bind("<ButtonRelease-1>", self.release)
        self.canvas.bind("<Button-3>", self.menu)
        asset = Path(__file__).with_name("assets") / "companion.png"
        if asset.is_file():
            original = tk.PhotoImage(file=str(asset))
            self.sprite: tk.PhotoImage | None = original.subsample(max(1, math.ceil(original.width()/240)))
        else:
            self.sprite = None
        self.controls = tk.Frame(root, bg=INK)
        for label, command in (("喂食", lambda: self.interact("feed")),
                               ("摸摸", lambda: self.interact("pet")),
                               ("委托", self.mission), ("工坊", self.workshop), ("×", self.close)):
            tk.Button(self.controls, text=label, command=command, bg=INK, fg="#f2eaff", activebackground="#493064",
                      activeforeground="white", relief="flat", font=("Microsoft YaHei UI", 10),
                      padx=8, pady=8, cursor="hand2").pack(side="left")
        self.canvas.create_window(160, 315, window=self.controls)
        threading.Thread(target=self.poll, daemon=True, name="genesis-pet-readonly").start()
        self.animate()

    def read_json(self, path: str) -> dict[str, Any]:
        opener = build_opener(ProxyHandler({}), NoRedirect())
        with opener.open(self.endpoint + path, timeout=2) as response:
            data = json.loads(response.read(512_000))
        if not isinstance(data, dict):
            raise ValueError("invalid lab response")
        return data

    def poll(self) -> None:
        while not self.stopping.is_set():
            try:
                health = self.read_json("/api/health")
                try:
                    session = self.read_json("/api/session")
                except HTTPError as error:
                    if error.code != 404:
                        raise
                    session = None
                update = task_mood(session, health.get("status") == "ready")
            except (OSError, ValueError, URLError):
                update = task_mood(None, False)
            with suppress(queue.Full):
                self.updates.put_nowait(update)
            self.stopping.wait(4)

    def interact(self, action: str) -> None:
        self.sleeping = action == "sleep"
        self.mood, self.message = self.pet.interact(action)
        self.until = time.monotonic() + 5
        try:
            self.pet.save(self.state_path)
        except OSError:
            self.message += "（本次未能保存互动记录）"

    def press(self, event: tk.Event[Any]) -> None:
        self.drag = event.x_root, event.y_root, self.root.winfo_x(), self.root.winfo_y()
        self.dragged = False

    def move(self, event: tk.Event[Any]) -> None:
        if self.drag is None:
            return
        x, y, left, top = self.drag
        dx, dy = event.x_root-x, event.y_root-y
        if abs(dx)+abs(dy) > 5:
            self.dragged = True
        new_x = max(0, min(self.root.winfo_screenwidth()-320, left+dx))
        new_y = max(0, min(self.root.winfo_screenheight()-350, top+dy))
        self.root.geometry(f"+{new_x}+{new_y}")

    def release(self, _event: tk.Event[Any]) -> None:
        if not self.dragged:
            self.interact("pet")
        self.drag = None

    def menu(self, event: tk.Event[Any]) -> None:
        menu = tk.Menu(self.root, tearoff=False)
        menu.add_command(label="休息一下", command=lambda: self.interact("sleep"))
        menu.add_checkbutton(label="安静模式", command=self.toggle_quiet)
        menu.add_separator()
        menu.add_command(label="退出桌宠", command=self.close)
        menu.tk_popup(event.x_root, event.y_root)

    def toggle_quiet(self) -> None:
        self.quiet = not self.quiet

    def mission(self) -> None:
        webbrowser.open(self.endpoint + "/")

    def workshop(self) -> None:
        webbrowser.open(self.endpoint + "/#workshop")

    def animate(self) -> None:
        if self.stopping.is_set():
            return
        with suppress(queue.Empty):
            self.task = self.updates.get_nowait()
        if not self.sleeping and time.monotonic() > self.until:
            self.mood, self.message = self.task
        self.canvas.delete("art")
        t = time.monotonic() - self.started
        amplitude = 2 if self.sleeping else 7
        y = 185 + amplitude * math.sin(t * 1.7)
        if self.mood in ("loved", "success", "eat"):
            y -= abs(math.sin(t*4))*10
        if self.sprite is not None:
            self.canvas.create_image(160, y, image=self.sprite, tags="art")
        else:
            # Functional fallback when an asset is unavailable, never hidden failure.
            self.canvas.create_oval(70, y-55, 250, y+55, fill="#8e63d9", outline=LILAC, width=3, tags="art")
            self.canvas.create_text(160, y, text="GENESIS", fill="white", tags="art")
        if not self.quiet:
            self.canvas.create_rectangle(12, 8, 308, 87, fill=INK, outline="#6e54ff", width=2, tags="art")
            self.canvas.create_text(160, 24, text="GENESIS / NOMI", fill=LILAC,
                                    font=("Microsoft YaHei UI", 9, "bold"), tags="art")
            self.canvas.create_text(160, 56, text=self.message, fill="#f7f0ff", width=266,
                                    font=("Microsoft YaHei UI", 10), tags="art")
        if self.mood == "sleep":
            self.canvas.create_text(237, 127, text="z Z", fill=LILAC, font=("Consolas", 18), tags="art")
        elif self.mood in ("loved", "success"):
            self.canvas.create_text(235, 130+math.sin(t*3)*6, text="✦", fill="#d8bdff",
                                    font=("Segoe UI", 24), tags="art")
        elif self.mood == "eat":
            self.canvas.create_oval(107, 245, 214, 263, fill="#493064", outline=LILAC, tags="art")
            self.canvas.create_text(160, 248, text="• • •", fill="#ffcfb4", font=("Segoe UI", 18), tags="art")
        self.root.after(50, self.animate)

    def close(self) -> None:
        self.stopping.set()
        self.root.destroy()


def main() -> int:
    parser = argparse.ArgumentParser(description="GENESIS independent desktop companion; DSH is optional and not required.")
    parser.add_argument("--lab-url", default="http://127.0.0.1:8000")
    data_dir = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "GENESIS"
    parser.add_argument("--state", type=Path, default=data_dir / "companion.json")
    parser.add_argument("--smoke-test", action="store_true", help="open the native window, then close after 1 second")
    parser.add_argument("--framed", action="store_true", help="show a normal title bar for accessibility/debugging")
    args = parser.parse_args()
    try:
        endpoint = local_endpoint(args.lab_url)
        root = tk.Tk()
        companion = Companion(root, endpoint, args.state)
        if args.framed:
            root.overrideredirect(False)
        if args.smoke_test:
            root.after(1000, companion.close)
        root.mainloop()
    except (ValueError, tk.TclError) as error:
        print(f"desktop companion could not start: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
