import os

from tdec.env import load_env_file


def test_load_env_file_sets_unset_values(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    path = tmp_path / ".env"
    path.write_text(
        """
# comment
OPENROUTER_API_KEY="abc123"
""",
        encoding="utf-8",
    )

    load_env_file(path)

    assert os.environ["OPENROUTER_API_KEY"] == "abc123"


def test_load_env_file_does_not_override_existing_values(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPENROUTER_API_KEY", "existing")
    path = tmp_path / ".env"
    path.write_text("OPENROUTER_API_KEY=new\n", encoding="utf-8")

    load_env_file(path)

    assert os.environ["OPENROUTER_API_KEY"] == "existing"
