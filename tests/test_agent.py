import json
from pathlib import Path

import httpx
import pytest
import respx

from mimo_coder.agent import Agent
from mimo_coder.client import MimoClient
from mimo_coder.tools import ToolBox


def _confirm_yes(*_: object) -> bool:
    return True


def _make_agent(tmp_path: Path) -> Agent:
    client = MimoClient(api_key="sk-test", base_url="https://api.test/v1")
    tools = ToolBox(root=tmp_path, confirm=_confirm_yes, auto=True, dry_run=False)
    return Agent(client=client, toolbox=tools, model="mimo-7b-rl", system="sys", max_turns=4)


@respx.mock
@pytest.mark.asyncio
async def test_agent_plain_text_answer(tmp_path: Path) -> None:
    respx.post("https://api.test/v1/chat/completions").mock(
        return_value=httpx.Response(
            200,
            json={
                "choices": [{"message": {"role": "assistant", "content": "hello world"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 2, "total_tokens": 12},
            },
        )
    )
    agent = _make_agent(tmp_path)
    agent.add_user("hi")
    out = await agent.run()
    assert out == "hello world"
    assert agent.state.usage.total_tokens == 12
    assert agent.state.turns == 1


@respx.mock
@pytest.mark.asyncio
async def test_agent_runs_tool_then_replies(tmp_path: Path) -> None:
    (tmp_path / "x.txt").write_text("alpha\nbeta\n")

    responses = iter(
        [
            httpx.Response(
                200,
                json={
                    "choices": [
                        {
                            "message": {
                                "role": "assistant",
                                "content": None,
                                "tool_calls": [
                                    {
                                        "id": "call_1",
                                        "type": "function",
                                        "function": {
                                            "name": "read_file",
                                            "arguments": json.dumps({"path": "x.txt"}),
                                        },
                                    }
                                ],
                            }
                        }
                    ],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 1, "total_tokens": 6},
                },
            ),
            httpx.Response(
                200,
                json={
                    "choices": [
                        {"message": {"role": "assistant", "content": "the file has 2 lines"}}
                    ],
                    "usage": {"prompt_tokens": 8, "completion_tokens": 5, "total_tokens": 13},
                },
            ),
        ]
    )
    respx.post("https://api.test/v1/chat/completions").mock(side_effect=lambda req: next(responses))

    agent = _make_agent(tmp_path)
    agent.add_user("read x.txt")
    out = await agent.run()
    assert "2 lines" in out
    assert agent.state.turns == 2
    assert agent.state.usage.total_tokens == 19
    # message order: system, user, assistant(tool_calls), tool, assistant
    roles = [m.role for m in agent.state.messages]
    assert roles == ["system", "user", "assistant", "tool", "assistant"]
