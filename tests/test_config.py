from chorba.config import Settings


def test_settings_reads_api_version_from_generated_file(monkeypatch, tmp_path):
    version_file = tmp_path / "_api_version.txt"
    version_file.write_text("0.1.0-abcdef0\n", encoding="utf-8")

    monkeypatch.setenv("DATABASE_URL", "postgresql://example/db")
    monkeypatch.delenv("API_VERSION", raising=False)
    monkeypatch.setattr("chorba.config._API_VERSION_FILE", version_file, raising=False)

    settings = Settings.from_env()

    assert settings.api_version == "0.1.0-abcdef0"
