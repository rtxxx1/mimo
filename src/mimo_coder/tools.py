"""Tools the agent can call. Each tool has:

  - a JSON-schema description (sent to the model)
  - a Python implementation (run locally)

Side-effecting tools (write_file, apply_patch, run_shell) gate on a confirm
callback supplied by the host so the CLI can prompt the user.
"""

from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ConfirmFn = Callable[[str, dict], bool]


@dataclass(slots=True)
class ToolResult:
    ok: bool
    output: str

    def to_message_content(self) -> str:
        if self.ok:
            return self.output
        return f"ERROR: {self.output}"


# ---------------------------------------------------------------------------
# Schemas (sent to MiMo as `tools=[...]`)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read a UTF-8 text file. Returns at most `limit` lines starting at `offset` (1-indexed).",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "offset": {"type": "integer", "minimum": 1, "default": 1},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 2000, "default": 500},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_dir",
            "description": "List entries of a directory (non-recursive). Returns lines like `[FILE] name` / `[DIR] name`.",
            "parameters": {
                "type": "object",
                "properties": {"path": {"type": "string", "default": "."}},
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "search",
            "description": "Regex search over the repo using ripgrep. Returns matching lines with file:line: prefix.",
            "parameters": {
                "type": "object",
                "properties": {
                    "pattern": {"type": "string"},
                    "path": {"type": "string", "default": "."},
                    "glob": {"type": "string", "description": "Optional glob filter, e.g. '*.py'"},
                },
                "required": ["pattern"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "write_file",
            "description": "Overwrite or create a file with the given UTF-8 content. Confirms unless --auto.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string"},
                    "content": {"type": "string"},
                },
                "required": ["path", "content"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apply_patch",
            "description": "Apply a unified diff (output of `diff -u`). Confirms unless --auto.",
            "parameters": {
                "type": "object",
                "properties": {"diff": {"type": "string"}},
                "required": ["diff"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_shell",
            "description": "Run a shell command in the repo root. Confirms unless --auto. Times out after 120s.",
            "parameters": {
                "type": "object",
                "properties": {
                    "command": {"type": "string"},
                    "timeout": {"type": "integer", "default": 120},
                },
                "required": ["command"],
            },
        },
    },
]


# ---------------------------------------------------------------------------
# Implementations
# ---------------------------------------------------------------------------


class ToolBox:
    """Bundles tool implementations with a confirm callback and root scope."""

    def __init__(
        self,
        root: Path,
        confirm: ConfirmFn,
        *,
        auto: bool = False,
        dry_run: bool = False,
    ) -> None:
        self.root = root.resolve()
        self.confirm = confirm
        self.auto = auto
        self.dry_run = dry_run

    # -- safety --------------------------------------------------------

    def _resolve(self, path: str) -> Path:
        p = (self.root / path).resolve() if not Path(path).is_absolute() else Path(path).resolve()
        if self.root not in p.parents and p != self.root:
            raise PermissionError(f"path escapes repo root: {path}")
        return p

    def _gate(self, name: str, args: dict) -> bool:
        if self.dry_run:
            return False
        if self.auto:
            return True
        return self.confirm(name, args)

    # -- read-only -----------------------------------------------------

    def read_file(self, path: str, offset: int = 1, limit: int = 500) -> ToolResult:
        try:
            p = self._resolve(path)
            text = p.read_text(encoding="utf-8", errors="replace").splitlines()
            chunk = text[offset - 1 : offset - 1 + limit]
            numbered = "\n".join(f"{offset + i}|{line}" for i, line in enumerate(chunk))
            suffix = f"\n... ({len(text) - (offset - 1 + len(chunk))} more lines)" if offset - 1 + len(chunk) < len(text) else ""
            return ToolResult(True, numbered + suffix)
        except Exception as e:
            return ToolResult(False, f"{type(e).__name__}: {e}")

    def list_dir(self, path: str = ".") -> ToolResult:
        try:
            p = self._resolve(path)
            if not p.is_dir():
                return ToolResult(False, f"not a directory: {path}")
            lines: list[str] = []
            for entry in sorted(p.iterdir(), key=lambda e: (e.is_file(), e.name.lower())):
                tag = "[DIR]" if entry.is_dir() else "[FILE]"
                lines.append(f"{tag} {entry.name}")
            return ToolResult(True, "\n".join(lines) or "(empty)")
        except Exception as e:
            return ToolResult(False, f"{type(e).__name__}: {e}")

    def search(self, pattern: str, path: str = ".", glob: str | None = None) -> ToolResult:
        try:
            target = self._resolve(path)
            cmd = ["rg", "--no-heading", "--line-number", "--color=never", pattern, str(target)]
            if glob:
                cmd[1:1] = ["--glob", glob]
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if r.returncode not in (0, 1):
                return ToolResult(False, r.stderr.strip() or f"rg exit {r.returncode}")
            return ToolResult(True, r.stdout or "(no matches)")
        except FileNotFoundError:
            return ToolResult(False, "ripgrep (rg) not installed")
        except Exception as e:
            return ToolResult(False, f"{type(e).__name__}: {e}")

    # -- side-effecting ------------------------------------------------

    def write_file(self, path: str, content: str) -> ToolResult:
        if not self._gate("write_file", {"path": path, "bytes": len(content)}):
            return ToolResult(False, "user declined or dry-run")
        try:
            p = self._resolve(path)
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_text(content, encoding="utf-8")
            return ToolResult(True, f"wrote {len(content)} bytes to {path}")
        except Exception as e:
            return ToolResult(False, f"{type(e).__name__}: {e}")

    def apply_patch(self, diff: str) -> ToolResult:
        if not self._gate("apply_patch", {"bytes": len(diff)}):
            return ToolResult(False, "user declined or dry-run")
        try:
            r = subprocess.run(
                ["git", "apply", "--whitespace=nowarn", "-"],
                input=diff,
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=30,
            )
            if r.returncode != 0:
                return ToolResult(False, r.stderr.strip() or "git apply failed")
            return ToolResult(True, "patch applied")
        except Exception as e:
            return ToolResult(False, f"{type(e).__name__}: {e}")

    def run_shell(self, command: str, timeout: int = 120) -> ToolResult:
        if not self._gate("run_shell", {"command": command}):
            return ToolResult(False, "user declined or dry-run")
        try:
            r = subprocess.run(
                command,
                shell=True,
                capture_output=True,
                text=True,
                cwd=self.root,
                timeout=timeout,
            )
            tail = (r.stdout + r.stderr).strip()
            if len(tail) > 8000:
                tail = tail[-8000:]
            status = f"exit={r.returncode}"
            return ToolResult(r.returncode == 0, f"{status}\n{tail}")
        except subprocess.TimeoutExpired:
            return ToolResult(False, f"timeout after {timeout}s")
        except Exception as e:
            return ToolResult(False, f"{type(e).__name__}: {e}")

    # -- dispatch ------------------------------------------------------

    def call(self, name: str, args: dict) -> ToolResult:
        method = {
            "read_file": self.read_file,
            "list_dir": self.list_dir,
            "search": self.search,
            "write_file": self.write_file,
            "apply_patch": self.apply_patch,
            "run_shell": self.run_shell,
        }.get(name)
        if not method:
            return ToolResult(False, f"unknown tool: {name}")
        try:
            return method(**args)
        except TypeError as e:
            return ToolResult(False, f"bad arguments for {name}: {e}")


def shell_quote(s: str) -> str:
    return shlex.quote(s)
