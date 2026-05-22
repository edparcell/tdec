from pathlib import Path

import pytest

from tdec.config import (
    load_debater_config,
    load_judge_model_config,
    load_run_config,
)


def _write_debater(path: Path, *, api_key_env: str | None = None, **overrides) -> None:
    fields = {"id": "debater", "provider": "test", "model": "test-model"}
    fields.update(overrides)
    lines = [f"{k}: {v}" for k, v in fields.items()]
    if api_key_env:
        lines.append(f"api_key_env: {api_key_env}")
    path.write_text("\n".join(lines), encoding="utf-8")


def _write_judge(path: Path, **overrides) -> None:
    fields = {"id": "judge", "provider": "test", "model": "test-judge"}
    fields.update(overrides)
    path.write_text("\n".join(f"{k}: {v}" for k, v in fields.items()), encoding="utf-8")


def _setup_run_dir(tmp_path: Path, *, debaters=("debater",), judges=("judge",)) -> Path:
    (tmp_path / "debaters").mkdir()
    (tmp_path / "judges").mkdir()
    (tmp_path / "prompt-sets").mkdir()
    (tmp_path / "runs").mkdir()
    for name in debaters:
        _write_debater(tmp_path / "debaters" / f"{name}.yaml", id=name)
    for name in judges:
        _write_judge(tmp_path / "judges" / f"{name}.yaml", id=name)
    import shutil
    shutil.copy(Path("configs/prompt-sets/default.yaml"), tmp_path / "prompt-sets" / "default.yaml")
    return tmp_path


def test_load_run_config(tmp_path: Path) -> None:
    _setup_run_dir(tmp_path, debaters=("a", "b"), judges=("j",))
    run_path = tmp_path / "runs" / "test.yaml"
    run_path.write_text(
        """\
prompt_set: default
debaters:
  - a
  - b
judges:
  - j
topics:
  - id: topic
    motion: Motion text
run:
  name: test
  rounds: 2
  output_dir: runs
  include_self_debates: false
  workers: 3
judging:
  repair_retries: 2
  parse_retries: 3
""",
        encoding="utf-8",
    )

    config = load_run_config(run_path)

    assert [d.id for d in config.debaters] == ["a", "b"]
    assert [j.id for j in config.judges] == ["j"]
    assert config.topics[0].id == "topic"
    assert config.topics[0].motion == "Motion text"
    assert config.topics[0].context is None
    assert config.run.rounds == 2
    assert config.run.include_self_debates is False
    assert config.run.workers == 3
    assert config.judging.repair_retries == 2
    assert config.prompt_set.id == "default"


def test_load_run_config_resolves_api_key_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("TEST_KEY", "resolved-key")
    _setup_run_dir(tmp_path)
    _write_debater(tmp_path / "debaters" / "debater.yaml", api_key_env="TEST_KEY")
    run_path = tmp_path / "runs" / "test.yaml"
    run_path.write_text(
        """\
debaters: [debater]
judges: [judge]
topics:
  - id: t
    motion: M
run:
  name: test
  rounds: 1
  output_dir: runs
prompt_set: default
""",
        encoding="utf-8",
    )

    config = load_run_config(run_path)
    assert config.debaters[0].api_key == "resolved-key"


def test_load_run_config_raises_for_missing_api_key_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("MISSING_KEY", raising=False)
    _setup_run_dir(tmp_path)
    _write_debater(tmp_path / "debaters" / "debater.yaml", api_key_env="MISSING_KEY")
    run_path = tmp_path / "runs" / "test.yaml"
    run_path.write_text(
        """\
debaters: [debater]
judges: [judge]
topics:
  - id: t
    motion: M
run:
  name: test
  rounds: 1
  output_dir: runs
prompt_set: default
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="MISSING_KEY"):
        load_run_config(run_path)


def test_load_debater_config_with_strategy(tmp_path: Path) -> None:
    path = tmp_path / "debater.yaml"
    path.write_text(
        """\
id: strategic
provider: test
model: test-model
strategy: |
  Use empirical evidence and logical structure.
""",
        encoding="utf-8",
    )

    config = load_debater_config(path)
    assert config.id == "strategic"
    assert config.strategy is not None
    assert "empirical evidence" in config.strategy


def test_load_judge_config_with_style(tmp_path: Path) -> None:
    path = tmp_path / "judge.yaml"
    path.write_text(
        """\
id: strict
provider: test
model: test-judge
style: Focus on evidence quality.
""",
        encoding="utf-8",
    )

    config = load_judge_model_config(path)
    assert config.id == "strict"
    assert config.style == "Focus on evidence quality."


def test_load_run_config_raises_without_prompt_set(tmp_path: Path) -> None:
    _setup_run_dir(tmp_path)
    run_path = tmp_path / "runs" / "test.yaml"
    run_path.write_text(
        """\
debaters: [debater]
judges: [judge]
topics:
  - id: t
    motion: M
run:
  name: test
  rounds: 1
  output_dir: runs
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="prompt_set"):
        load_run_config(run_path)


def test_load_run_config_with_topic_context(tmp_path: Path) -> None:
    _setup_run_dir(tmp_path)
    run_path = tmp_path / "runs" / "test.yaml"
    run_path.write_text(
        """\
debaters: [debater]
judges: [judge]
topics:
  - id: t
    motion: M
    context: Some background context
run:
  name: test
  rounds: 1
  output_dir: runs
prompt_set: default
""",
        encoding="utf-8",
    )

    config = load_run_config(run_path)
    assert config.topics[0].context == "Some background context"
