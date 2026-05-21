from pathlib import Path

import pytest

from tdec.config import load_tournament_config


def test_load_tournament_config() -> None:
    config = load_tournament_config(Path("configs/tournament.yaml"))

    assert config.run.rounds == 3
    assert config.topics[0].id == "trump_administration_policies"
    assert [model.id for model in config.debaters] == [
        "local_tinyllama_a",
        "local_tinyllama_b",
    ]
    assert config.judges[0].id == "local_tinyllama_judge"
    assert config.judging.repair_retries == 1
    assert config.judging.parse_retries == 1


def test_load_tournament_config_resolves_api_key_env(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  name: test
  rounds: 1
  output_dir: runs
judging:
  repair_retries: 2
  parse_retries: 3
topics:
  - id: topic
    motion: Motion
    pro_position: Pro
    con_position: Con
debaters:
  - id: debater
    provider: openrouter
    model: ibm-granite/granite-4.1-8b
    api_key_env: OPENROUTER_API_KEY
judges:
  - id: judge
    provider: openrouter
    model: inclusionai/ring-2.6-1t
    api_key_env: OPENROUTER_API_KEY
""",
        encoding="utf-8",
    )

    config = load_tournament_config(config_path)

    assert config.debaters[0].api_key == "test-key"
    assert config.judges[0].api_key == "test-key"
    assert config.judging.repair_retries == 2
    assert config.judging.parse_retries == 3


def test_load_tournament_config_raises_for_missing_api_key_env(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    config_path = tmp_path / "config.yaml"
    config_path.write_text(
        """
run:
  name: test
  rounds: 1
  output_dir: runs
topics:
  - id: topic
    motion: Motion
    pro_position: Pro
    con_position: Con
debaters:
  - id: debater
    provider: openrouter
    model: ibm-granite/granite-4.1-8b
    api_key_env: OPENROUTER_API_KEY
judges:
  - id: judge
    provider: openrouter
    model: inclusionai/ring-2.6-1t
    api_key_env: OPENROUTER_API_KEY
""",
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="OPENROUTER_API_KEY"):
        load_tournament_config(config_path)
