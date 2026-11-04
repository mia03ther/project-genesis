"""Local interactions and honest projections of the lab's authoritative state."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


def local_endpoint(value: str) -> str:
    parsed = urlsplit(value)
    if (parsed.scheme != "http" or parsed.hostname != "127.0.0.1" or parsed.username
            or parsed.password or parsed.path not in ("", "/") or parsed.query or parsed.fragment):
        raise ValueError("desktop companion only connects to http://127.0.0.1:<port>")
    if parsed.port is None:
        raise ValueError("specify the local lab port")
    return value.rstrip("/")


def task_mood(session: dict[str, Any] | None, connected: bool) -> tuple[str, str]:
    if not connected:
        return "offline", "实验室还没连接。我先陪你待一会。"
    if session is None:
        return "idle", "今天有一封可疑付款委托。要一起看看吗？"
    result = session.get("result")
    if session.get("stage") == "replayed" and isinstance(result, dict):
        if result.get("passed") is True:
            return "success", "你守住了付款意图！本地裁判已验证。"
        return "retry", "这次没守住。可以回溯，我们再试一次。"
    if session.get("stage") == "diagnosed":
        return "ready", "规则已选好。等你决定是否开始实验。"
    return "investigating", "我帮你守着委托。别只看地址的缩写。"


@dataclass
class PetState:
    meals: int = 0
    cuddles: int = 0

    @classmethod
    def load(cls, path: Path) -> PetState:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return cls()
            values = [data.get(key, 0) for key in ("meals", "cuddles")]
            if any(type(value) is not int or not 0 <= value <= 1_000_000 for value in values):
                return cls()
            return cls(*values)
        except (OSError, ValueError, TypeError):
            return cls()

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"format_version": 1, "meals": self.meals, "cuddles": self.cuddles}),
                             encoding="utf-8")
        os.replace(temporary, path)

    def interact(self, action: str) -> tuple[str, str]:
        if action == "feed":
            self.meals = min(1_000_000, self.meals + 1)
            return "eat", "收到小点心！今天也有好好陪着你。"
        if action == "pet":
            self.cuddles = min(1_000_000, self.cuddles + 1)
            return "loved", "再摸一下。我保证不替你乱签名。"
        if action == "sleep":
            return "sleep", "休息一下。点我就能叫醒我。"
        raise ValueError("unknown pet interaction")
