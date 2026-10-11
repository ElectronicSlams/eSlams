import pytest


@pytest.fixture
def arena_session_env(monkeypatch):
    monkeypatch.setenv("ESLAMS_ARENA_SESSION_SECRET", "arena-session-test-secret-32chars-ok")
    for name in ("ESLAMS_ENV", "ESLAMS_ARENA_SESSION_ALLOW_DEVELOPMENT_SECRET",
                 "ESLAMS_ARENA_SESSION_KEY_ID", "ESLAMS_ARENA_SESSION_MAX_AGE_SECONDS"):
        monkeypatch.delenv(name, raising=False)
