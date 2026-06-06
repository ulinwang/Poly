"""Backend smoke tests — database + models."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from database import get_db
from models.settings import ApiSettings


def test_database_api_settings():
    """SQLite CRUD for api_settings."""
    with get_db() as db:
        db.execute(
            "INSERT INTO api_settings (provider, model, api_key, temperature, max_tokens) "
            "VALUES (?, ?, ?, ?, ?)",
            ("deepseek", "deepseek-chat", "sk-test", 0.7, 2048),
        )
        db.commit()
        cur = db.execute(
            "SELECT provider, model FROM api_settings WHERE id = last_insert_rowid()"
        )
        row = cur.fetchone()
        assert tuple(row) == ("deepseek", "deepseek-chat")

        # Cleanup
        db.execute("DELETE FROM api_settings WHERE api_key = 'sk-test'")
        db.commit()


def test_api_settings_model_json():
    s = ApiSettings(
        provider="openai", model="gpt-4o", api_key="x",
        temperature=0.5, max_tokens=1024
    )
    assert s.provider == "openai"
    assert s.model == "gpt-4o"
    d = s.model_dump()
    assert d["provider"] == "openai"
    assert d["model"] == "gpt-4o"
    assert d["temperature"] == 0.5
