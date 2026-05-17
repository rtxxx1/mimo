"""Configuration loading for mimo-coder.

Resolution order (later overrides earlier):
  1. Built-in defaults
  2. ~/.mimo/config.toml      (user-global)
  3. ./.mimorc                (repo-local)
  4. Environment variables    (MIMO_*)
  5. CLI flags (applied by the caller)
"""

from __future__ import annotations

import contextlib
import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - fallback for 3.10
    import tomli as tomllib


DEFAULTS: dict[str, object] = {
    "base_url": "https://api.xiaomimimo.com/v1",
    "model": "mimo-7b-rl",
    "max_turns": 12,
    "temperature": 0.2,
    "system": (
        "You are mimo-coder, a careful terminal coding agent. "
        "Read code before changing it. Prefer small, verifiable diffs. "
        "When you are unsure about a path or symbol, call a tool to check."
    ),
    "pin": [],
}


@dataclass(slots=True)
class Config:
    api_key: str | None = None
    base_url: str = str(DEFAULTS["base_url"])
    model: str = str(DEFAULTS["model"])
    max_turns: int = int(DEFAULTS["max_turns"])  # type: ignore[arg-type]
    temperature: float = float(DEFAULTS["temperature"])  # type: ignore[arg-type]
    system: str = str(DEFAULTS["system"])
    pin: list[str] = field(default_factory=list)
    auto: bool = False
    dry_run: bool = False

    def require_api_key(self) -> str:
        if not self.api_key:
            raise RuntimeError(
                "MIMO_API_KEY is not set. Get one at https://platform.xiaomimimo.com/ "
                "and `export MIMO_API_KEY=sk-...`."
            )
        return self.api_key


def _load_toml(path: Path) -> dict:
    if not path.is_file():
        return {}
    with path.open("rb") as f:
        return tomllib.load(f)


def load_config(repo_root: Path | None = None) -> Config:
    cfg = Config()

    user_cfg = _load_toml(Path.home() / ".mimo" / "config.toml")
    repo_cfg = _load_toml((repo_root or Path.cwd()) / ".mimorc")

    for src in (user_cfg, repo_cfg):
        for key in ("base_url", "model", "system"):
            if isinstance(src.get(key), str):
                setattr(cfg, key, src[key])
        if isinstance(src.get("max_turns"), int):
            cfg.max_turns = src["max_turns"]
        if isinstance(src.get("temperature"), (int, float)):
            cfg.temperature = float(src["temperature"])
        if isinstance(src.get("pin"), list):
            cfg.pin = [str(p) for p in src["pin"]]

    # Env overrides
    cfg.api_key = os.environ.get("MIMO_API_KEY") or cfg.api_key
    cfg.base_url = os.environ.get("MIMO_BASE_URL") or cfg.base_url
    cfg.model = os.environ.get("MIMO_MODEL") or cfg.model
    if v := os.environ.get("MIMO_MAX_TURNS"):
        with contextlib.suppress(ValueError):
            cfg.max_turns = int(v)

    return cfg
