from pathlib import Path

from mimo_coder.tools import ToolBox, ToolResult


def make_tools(tmp_path: Path, *, auto: bool = True) -> ToolBox:
    return ToolBox(root=tmp_path, confirm=lambda *_: True, auto=auto, dry_run=False)


def test_read_file_paginates(tmp_path: Path) -> None:
    p = tmp_path / "a.txt"
    p.write_text("\n".join(f"line{i}" for i in range(1, 11)))
    tools = make_tools(tmp_path)
    r = tools.read_file("a.txt", offset=3, limit=2)
    assert r.ok
    lines = r.output.splitlines()
    assert lines[0].startswith("3|line3")
    assert lines[1].startswith("4|line4")
    assert "more lines" in r.output


def test_read_file_missing(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    r = tools.read_file("nope.txt")
    assert not r.ok
    assert "FileNotFoundError" in r.output or "No such file" in r.output


def test_list_dir(tmp_path: Path) -> None:
    (tmp_path / "sub").mkdir()
    (tmp_path / "f.txt").write_text("x")
    tools = make_tools(tmp_path)
    r = tools.list_dir(".")
    assert r.ok
    assert "[DIR] sub" in r.output
    assert "[FILE] f.txt" in r.output


def test_write_file_gated(tmp_path: Path) -> None:
    tools = ToolBox(root=tmp_path, confirm=lambda *_: False, auto=False, dry_run=False)
    r = tools.write_file("new.txt", "hello")
    assert not r.ok
    assert not (tmp_path / "new.txt").exists()


def test_write_file_auto(tmp_path: Path) -> None:
    tools = make_tools(tmp_path, auto=True)
    r = tools.write_file("new.txt", "hello")
    assert r.ok
    assert (tmp_path / "new.txt").read_text() == "hello"


def test_path_escape_blocked(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    r = tools.read_file("../../../etc/passwd")
    assert not r.ok
    assert "escapes" in r.output or "PermissionError" in r.output


def test_dry_run_blocks_writes(tmp_path: Path) -> None:
    tools = ToolBox(root=tmp_path, confirm=lambda *_: True, auto=True, dry_run=True)
    r = tools.write_file("x.txt", "hi")
    assert not r.ok
    assert not (tmp_path / "x.txt").exists()


def test_unknown_tool(tmp_path: Path) -> None:
    tools = make_tools(tmp_path)
    r = tools.call("does_not_exist", {})
    assert isinstance(r, ToolResult)
    assert not r.ok
