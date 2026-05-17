"""Typer-based CLI."""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Confirm, Prompt
from rich.syntax import Syntax

from .__about__ import __version__
from .agent import Agent
from .client import MimoClient
from .config import load_config
from .sessions import list_sessions, load_session, save_session
from .tools import ToolBox

app = typer.Typer(
    add_completion=False,
    help="mimo-coder: a minimal terminal coding agent powered by Xiaomi MiMo models.",
    no_args_is_help=False,
)
console = Console()

_PROMPT_ARG = typer.Argument(None, help="The instruction to send.")


def _confirm(name: str, args: dict) -> bool:
    if name == "run_shell":
        cmd = args.get("command", "")
        console.print(Panel(Syntax(cmd, "bash"), title="run_shell", border_style="yellow"))
    elif name == "write_file":
        console.print(
            Panel(
                f"[bold]path:[/bold] {args.get('path')}\n[bold]bytes:[/bold] {args.get('bytes', '?')}",
                title="write_file",
                border_style="yellow",
            )
        )
    elif name == "apply_patch":
        console.print(Panel(f"diff bytes: {args.get('bytes', '?')}", title="apply_patch", border_style="yellow"))
    return Confirm.ask(f"Run [bold]{name}[/bold]?", default=False)


def _make_agent(*, model_override: str | None = None, auto: bool = False, dry_run: bool = False) -> Agent:
    cfg = load_config()
    cfg.auto = auto
    cfg.dry_run = dry_run
    if model_override:
        cfg.model = model_override

    client = MimoClient(api_key=cfg.require_api_key(), base_url=cfg.base_url)
    tools = ToolBox(root=Path.cwd(), confirm=_confirm, auto=cfg.auto, dry_run=cfg.dry_run)
    agent = Agent(
        client=client,
        toolbox=tools,
        model=cfg.model,
        system=cfg.system,
        temperature=cfg.temperature,
        max_turns=cfg.max_turns,
    )

    # Pin files: prepend a system note + read each pinned file as a tool result.
    if cfg.pin:
        agent.state.messages[0].content = (
            (agent.state.messages[0].content or "")
            + "\n\nRepo-pinned files (always relevant):\n- "
            + "\n- ".join(cfg.pin)
        )
    return agent


def _on_event(kind: str, payload: dict) -> None:
    if kind == "assistant_text":
        text = payload["text"] or ""
        if text.strip():
            console.print(Markdown(text))
    elif kind == "tool_call":
        console.print(f"[cyan]→ tool[/cyan] {payload['name']} {payload['args']}")
    elif kind == "tool_result":
        ok = payload["ok"]
        head = payload["output"].splitlines()[:6]
        body = "\n".join(head)
        console.print(
            Panel(
                body,
                title=f"{'✓' if ok else '✗'} {payload['name']}",
                border_style="green" if ok else "red",
                expand=False,
            )
        )


@app.command()
def version() -> None:
    """Print version and exit."""
    console.print(f"mimo-coder {__version__}")


@app.command()
def run(
    prompt: list[str] = _PROMPT_ARG,
    model: str | None = typer.Option(None, "--model", "-m", help="Override MIMO_MODEL."),
    auto: bool = typer.Option(False, "--auto", help="Skip confirmations for side-effecting tools."),
    dry_run: bool = typer.Option(False, "--dry-run", help="Refuse all side-effecting tools."),
) -> None:
    """Run a single instruction and print the answer."""
    if not prompt:
        console.print("[red]error[/red]: provide a prompt, or use `mimo repl`.")
        raise typer.Exit(2)
    text = " ".join(prompt)
    agent = _make_agent(model_override=model, auto=auto, dry_run=dry_run)
    agent.add_user(text)
    asyncio.run(agent.run(on_event=_on_event))
    u = agent.state.usage
    console.print(
        f"\n[dim]turns={agent.state.turns}  prompt={u.prompt_tokens}  completion={u.completion_tokens}  total={u.total_tokens}[/dim]"
    )


@app.command()
def repl(
    model: str | None = typer.Option(None, "--model", "-m"),
    auto: bool = typer.Option(False, "--auto"),
    dry_run: bool = typer.Option(False, "--dry-run"),
    resume: str | None = typer.Option(None, "--resume", help="Resume a saved session by name."),
) -> None:
    """Interactive REPL with persistent conversation."""
    agent = _make_agent(model_override=model, auto=auto, dry_run=dry_run)
    if resume:
        try:
            data = load_session(resume)
        except FileNotFoundError:
            console.print(f"[red]no such session:[/red] {resume}")
            raise typer.Exit(1) from None
        from .agent import Turn

        agent.state.messages = [Turn(**m) for m in data["messages"]]
        console.print(f"[dim]resumed session[/dim] [bold]{resume}[/bold] ({len(data['messages'])} turns)")

    console.print(
        Panel.fit(
            f"mimo-coder {__version__} · model={agent.model}\n"
            "Commands: /save <name>  /load <name>  /sessions  /clear  /quit",
            border_style="magenta",
        )
    )
    while True:
        try:
            line = Prompt.ask("[bold magenta]>[/bold magenta]")
        except (EOFError, KeyboardInterrupt):
            console.print()
            return
        if not line.strip():
            continue
        if line.startswith("/"):
            parts = line.split(maxsplit=1)
            cmd = parts[0]
            arg = parts[1] if len(parts) > 1 else ""
            if cmd == "/quit":
                return
            if cmd == "/sessions":
                names = list_sessions() or ["(none)"]
                console.print("\n".join(names))
                continue
            if cmd == "/save":
                name = arg.strip() or "default"
                p = save_session(
                    name,
                    [m.to_openai() for m in agent.state.messages],
                    meta={"model": agent.model},
                )
                console.print(f"[dim]saved → {p}[/dim]")
                continue
            if cmd == "/load":
                name = arg.strip()
                if not name:
                    console.print("[red]usage:[/red] /load <name>")
                    continue
                from .agent import Turn

                data = load_session(name)
                agent.state.messages = [Turn(**m) for m in data["messages"]]
                console.print(f"[dim]loaded {name} ({len(data['messages'])} msgs)[/dim]")
                continue
            if cmd == "/clear":
                sys_msg = agent.state.messages[0]
                agent.state.messages = [sys_msg]
                console.print("[dim]conversation cleared[/dim]")
                continue
            console.print(f"[red]unknown command:[/red] {cmd}")
            continue

        agent.add_user(line)
        asyncio.run(agent.run(on_event=_on_event))


@app.command()
def doctor() -> None:
    """Diagnose configuration."""
    cfg = load_config()
    rows = [
        ("MIMO_API_KEY", "set" if cfg.api_key else "[red]MISSING[/red]"),
        ("base_url", cfg.base_url),
        ("model", cfg.model),
        ("max_turns", str(cfg.max_turns)),
        ("temperature", str(cfg.temperature)),
        ("repo", str(Path.cwd())),
    ]
    for k, v in rows:
        console.print(f"  [bold]{k:<14}[/bold] {v}")
    if not cfg.api_key:
        sys.exit(1)


def main() -> None:  # pragma: no cover
    app()


if __name__ == "__main__":  # pragma: no cover
    main()
