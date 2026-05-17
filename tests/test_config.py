from mimo_coder.config import load_config


def test_env_overrides(monkeypatch, tmp_path) -> None:
    monkeypatch.setenv("MIMO_API_KEY", "sk-env")
    monkeypatch.setenv("MIMO_MODEL", "mimo-vl")
    monkeypatch.setenv("MIMO_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("MIMO_MAX_TURNS", "7")
    cfg = load_config(repo_root=tmp_path)
    assert cfg.api_key == "sk-env"
    assert cfg.model == "mimo-vl"
    assert cfg.base_url == "https://example.test/v1"
    assert cfg.max_turns == 7


def test_repo_rc_overrides_defaults(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("MIMO_MODEL", raising=False)
    (tmp_path / ".mimorc").write_text(
        'model = "mimo-coder"\nmax_turns = 9\npin = ["a.py", "b.py"]\n'
    )
    cfg = load_config(repo_root=tmp_path)
    assert cfg.model == "mimo-coder"
    assert cfg.max_turns == 9
    assert cfg.pin == ["a.py", "b.py"]


def test_require_api_key_raises(monkeypatch, tmp_path) -> None:
    monkeypatch.delenv("MIMO_API_KEY", raising=False)
    cfg = load_config(repo_root=tmp_path)
    try:
        cfg.require_api_key()
    except RuntimeError as e:
        assert "MIMO_API_KEY" in str(e)
    else:
        raise AssertionError("expected RuntimeError")
