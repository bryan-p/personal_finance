from app.core.config import Settings


def test_https_proxy_settings_are_configurable():
    settings = Settings(
        _env_file=None,
        secret_key="deployment-test-secret",
        database_name="fintracker",
        database_user="fintracker",
        database_password="test-password",
        api_root_path="/api",
        cookie_secure=True,
        cors_origins="https://finance.example.com",
    )

    assert settings.api_root_path == "/api"
    assert settings.cookie_secure is True
    assert settings.allowed_origins[0] == "https://finance.example.com"

