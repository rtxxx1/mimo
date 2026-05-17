"""Persist conversation transcripts to ~/.mimo/sessions/<name>.json."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any


def sessions_dir() -> Path:
    p = Path.home() / ".mimo" / "sessions"
    p.mkdir(parents=True, exist_ok=True)
    return p


def save_session(name: str, messages: list[dict[str, Any]], meta: dict | None = None) -> Path:
    path = sessions_dir() / f"{name}.json"
    payload = {
        "saved_at": time.time(),
        "meta": meta or {},
        "messages": messages,
    }
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return path


def load_session(name: str) -> dict[str, Any]:
    path = sessions_dir() / f"{name}.json"
    return json.loads(path.read_text(encoding="utf-8"))


def list_sessions() -> list[str]:
    return sorted(p.stem for p in sessions_dir().glob("*.json"))
