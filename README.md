# mimo-coder

A minimal, hackable terminal coding agent powered by Xiaomi **MiMo** models. Drop into any repo, ask it to read code, propose patches, run shell commands, or scaffold a feature, and it streams the answer back with proper tool-use over the OpenAI-compatible MiMo Chat Completions API.

```
$ mimo "find all TODO comments in src/ and group them by file"
$ mimo --auto "add a CLI flag --json to the report command, write a test, run pytest"
$ mimo /repl     # interactive REPL with persistent conversation
```

## Why

The 100T event ships free MiMo capacity for builders. A coding agent is the fastest way to put that capacity to real work: every prompt invokes the model, every tool call burns tokens against a real workload, and the resulting trace is reproducible. mimo-coder is small enough to read in one sitting and structured well enough to extend — bring your own tool, your own sandbox, your own model preset.

## Features

- **Native tool-use loop** over MiMo Chat Completions (`tools=[...]`), with safe-by-default file/exec sandboxing.
- **Streaming responses** — partial deltas land as they arrive, no lag waiting for the final token.
- **Repo-aware context** — `.mimorc` lets you pin files, set a system prompt, and choose a model preset per project.
- **Diff-first edits** — the agent proposes unified diffs; nothing touches disk until you confirm (or pass `--auto`).
- **REPL mode** with conversation history persisted to `~/.mimo/sessions/`.
- **Cost meter** — token usage per turn and per session.
- **Zero heavy deps** — `httpx`, `rich`, `typer`, `pydantic`. That's it.

## Install

```bash
git clone https://github.com/rtxxx1/mimo.git
cd mimo
pip install -e .
```

Set your MiMo API key:

```bash
export MIMO_API_KEY="sk-..."           # from https://platform.xiaomimimo.com/
export MIMO_BASE_URL="https://api.xiaomimimo.com/v1"   # optional override
export MIMO_MODEL="mimo-7b-rl"         # default; also: mimo-vl, mimo-coder, etc.
```

## Quick start

```bash
mimo "summarize the public API of this repo in 5 bullets"
mimo --model mimo-coder "refactor src/utils.py to use pathlib"
mimo --auto "run the tests and fix the first failing one"
mimo /repl
```

In REPL:

```
> read pyproject.toml
> what python version is required?
> /save my-session
> /quit
```

## Tools the agent can call

| Tool             | Effect                                          | Sandbox |
|------------------|-------------------------------------------------|---------|
| `read_file`      | Read a file with line numbers + pagination      | RO      |
| `list_dir`       | List a directory tree                           | RO      |
| `search`         | ripgrep over the repo                           | RO      |
| `write_file`     | Overwrite or create a file                      | confirm |
| `apply_patch`    | Apply a unified diff                            | confirm |
| `run_shell`      | Run a shell command                             | confirm |

`--auto` skips confirmation. `--dry-run` prints what would run and exits.

## Config (`.mimorc`)

```toml
model = "mimo-coder"
system = "You are a careful Python engineer. Write tests before code."
pin = ["pyproject.toml", "src/mimo_coder/agent.py"]
max_turns = 12
```

## Roadmap

- Vision tool routing to `mimo-vl` for screenshots/diagrams.
- Local cache of tool outputs keyed by content hash.
- Plugin entry points (`mimo_coder.tools`) so you can ship your own tool as a separate package.

## License

MIT. See [LICENSE](LICENSE).
