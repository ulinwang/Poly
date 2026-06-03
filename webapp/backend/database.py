"""SQLite database for user settings and experiment history."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Optional

DB_PATH = Path(__file__).parent / "data" / "webapp.db"


def _init_db(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS api_settings (
            id INTEGER PRIMARY KEY,
            provider TEXT NOT NULL,
            model TEXT NOT NULL,
            api_key TEXT NOT NULL,
            base_url TEXT,
            temperature REAL DEFAULT 0.7,
            max_tokens INTEGER DEFAULT 2048,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE TABLE IF NOT EXISTS experiments (
            id TEXT PRIMARY KEY,
            slug TEXT NOT NULL,
            n_agents INTEGER NOT NULL,
            n_ticks INTEGER NOT NULL,
            persona_set TEXT NOT NULL,
            api_settings_id INTEGER REFERENCES api_settings(id),
            status TEXT NOT NULL,
            started_at TIMESTAMP,
            finished_at TIMESTAMP,
            result_summary TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        );

        CREATE INDEX IF NOT EXISTS idx_experiments_status ON experiments(status);
        CREATE INDEX IF NOT EXISTS idx_experiments_slug ON experiments(slug);
        """
    )
    conn.commit()


@contextmanager
def get_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    try:
        _init_db(conn)
        yield conn
        conn.commit()
    finally:
        conn.close()


def get_api_settings() -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM api_settings ORDER BY updated_at DESC LIMIT 1"
        ).fetchone()
        if row:
            return dict(row)
        return None


def save_api_settings(settings: dict) -> int:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO api_settings (provider, model, api_key, base_url, temperature, max_tokens)
            VALUES (:provider, :model, :api_key, :base_url, :temperature, :max_tokens)
            ON CONFLICT(id) DO UPDATE SET
                provider=:provider, model=:model, api_key=:api_key,
                base_url=:base_url, temperature=:temperature, max_tokens=:max_tokens,
                updated_at=CURRENT_TIMESTAMP
            """,
            settings,
        )
        return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def save_experiment(exp: dict) -> None:
    with get_db() as conn:
        conn.execute(
            """
            INSERT INTO experiments (id, slug, n_agents, n_ticks, persona_set, status, started_at)
            VALUES (:id, :slug, :n_agents, :n_ticks, :persona_set, :status, :started_at)
            ON CONFLICT(id) DO UPDATE SET
                status=:status, finished_at=:finished_at, result_summary=:result_summary
            """,
            exp,
        )


def get_experiments(limit: int = 100) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_experiment(exp_id: str) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM experiments WHERE id = ?", (exp_id,)
        ).fetchone()
        return dict(row) if row else None
