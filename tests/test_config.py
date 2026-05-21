from pathlib import Path

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

