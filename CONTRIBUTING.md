# Contributing

Thanks for thinking about contributing.

## Dev setup

```bash
git clone https://github.com/rtxxx1/mimo.git
cd mimo
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

## Layout

```
src/mimo_coder/
  __about__.py     version
  __init__.py
  __main__.py      `python -m mimo_coder`
  agent.py         the ReAct loop
  cli.py           Typer commands (run, repl, doctor)
  client.py        async MiMo / OpenAI-compatible client
  config.py        defaults + ~/.mimo/config.toml + .mimorc + env
  sessions.py      transcript persistence
  tools.py         tool schemas + ToolBox dispatch
tests/             pytest + respx, no real network
```

## Adding a tool

1. Append a JSON-schema entry to `TOOL_SCHEMAS` in `tools.py`.
2. Implement a method on `ToolBox` returning a `ToolResult`.
3. Register the method in `ToolBox.call`.
4. Add a test in `tests/test_tools.py`.

Side-effecting tools must call `self._gate(name, args)` before doing anything.

## Running the suite

```bash
ruff check .
pytest -q
```

## Style

- Python 3.10+, type-hinted.
- Line length 100.
- Async I/O via `httpx`.
- Side effects gated through `ToolBox._gate`.
