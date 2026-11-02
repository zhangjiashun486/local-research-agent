import json

import pytest

from local_app import settings


@pytest.fixture
def isolated_repo(monkeypatch, tmp_path):
    for key in ("LOCAL_RESEARCH_CONFIG", "LOCAL_RESEARCH_BASE_URL", "LOCAL_RESEARCH_MODEL"):
        monkeypatch.delenv(key, raising=False)
    repo = tmp_path / "standalone-repo"
    repo.mkdir()
    monkeypatch.setattr(settings, "ROOT", repo)
    return repo


def test_repository_configuration_does_not_depend_on_parent_file(isolated_repo):
    (isolated_repo.parent / "local-model-connection.json").write_text('{"model":"wrong-parent"}', encoding="utf-8")
    (isolated_repo / "local-model-connection.json").write_text('{"model":"repo-model","base_url":"http://localhost:1235/v1"}', encoding="utf-8")
    assert settings.load_model_settings()["model"] == "repo-model"


def test_environment_can_run_without_any_config_file(isolated_repo, monkeypatch):
    monkeypatch.setenv("LOCAL_RESEARCH_MODEL", "environment-model")
    assert settings.load_model_settings() == {"model":"environment-model", "base_url":"http://127.0.0.1:1235/v1"}


def test_environment_overrides_repo_configuration(isolated_repo, monkeypatch):
    (isolated_repo / "local-model-connection.json").write_text(json.dumps({"model":"repo-model"}), encoding="utf-8")
    monkeypatch.setenv("LOCAL_RESEARCH_MODEL", "override-model")
    monkeypatch.setenv("LOCAL_RESEARCH_BASE_URL", "http://localhost:1234/v1/")
    assert settings.load_model_settings() == {"model":"override-model", "base_url":"http://localhost:1234/v1"}


def test_missing_model_has_actionable_error_instead_of_using_parent(isolated_repo):
    (isolated_repo.parent / "local-model-connection.json").write_text('{"model":"wrong-parent"}', encoding="utf-8")
    with pytest.raises(ValueError, match="LOCAL_RESEARCH_MODEL"):
        settings.load_model_settings()
