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
    # Gracefully add result columns if they don't exist yet
    for col, typ in (
        ("final_yes_mid", "REAL"),
        ("total_fills", "INTEGER"),
        ("total_actions", "INTEGER"),
        ("avg_tick_time_ms", "REAL"),
    ):
        try:
            conn.execute(f"ALTER TABLE experiments ADD COLUMN {col} {typ}")
        except sqlite3.OperationalError:
            pass  # column already exists
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


_ALLOWED_COLS = frozenset({
    "id", "slug", "n_agents", "n_ticks", "persona_set",
    "api_settings_id", "status", "started_at", "finished_at",
    "result_summary", "created_at",
    "final_yes_mid", "total_fills", "total_actions", "avg_tick_time_ms",
})


def save_experiment(exp: dict) -> None:
    if "id" not in exp:
        raise ValueError("id is required")
    # Strip keys that don't belong to the table (e.g. elapsed_s)
    clean = {k: v for k, v in exp.items() if k in _ALLOWED_COLS}
    update_keys = [k for k in clean.keys() if k != "id"]
    with get_db() as conn:
        if update_keys:
            set_clause = ", ".join(f"{k}=:{k}" for k in update_keys)
            cur = conn.execute(
                f"UPDATE experiments SET {set_clause} WHERE id = :id",
                clean,
            )
            if cur.rowcount:
                return
        # Fallback to INSERT
        keys = list(clean.keys())
        cols = ", ".join(keys)
        placeholders = ", ".join(f":{k}" for k in keys)
        conn.execute(
            f"INSERT INTO experiments ({cols}) VALUES ({placeholders})",
            clean,
        )


def get_experiments(limit: int = 100) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM experiments ORDER BY created_at DESC LIMIT ?",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]


def get_experiments_filtered(
    status: Optional[str] = None,
    slug: Optional[str] = None,
    limit: int = 20,
    offset: int = 0,
) -> tuple[list[dict], int]:
    with get_db() as conn:
        where_clauses: list[str] = []
        params: list = []
        if status:
            where_clauses.append("status = ?")
            params.append(status)
        if slug:
            where_clauses.append("slug LIKE ?")
            params.append(f"%{slug}%")
        where = " WHERE " + " AND ".join(where_clauses) if where_clauses else ""
        rows = conn.execute(
            f"SELECT * FROM experiments {where} ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (*params, limit, offset),
        ).fetchall()
        total_row = conn.execute(
            f"SELECT COUNT(*) FROM experiments {where}",
            params,
        ).fetchone()
        total = total_row[0] if total_row else 0
        return [dict(r) for r in rows], total


def search_experiments(q: str, limit: int = 20) -> list[dict]:
    with get_db() as conn:
        rows = conn.execute(
            "SELECT * FROM experiments WHERE slug LIKE ? ORDER BY created_at DESC LIMIT ?",
            (f"%{q}%", limit),
        ).fetchall()
        return [dict(r) for r in rows]


def get_experiment_stats() -> dict:
    with get_db() as conn:
        row = conn.execute(
            """
            SELECT
                COUNT(*) AS total_runs,
                SUM(CASE WHEN status = 'running' THEN 1 ELSE 0 END) AS running_count,
                AVG(n_agents) AS avg_agents,
                AVG(n_ticks) AS avg_ticks
            FROM experiments
            """
        ).fetchone()
        return {
            "total_runs": row["total_runs"] or 0,
            "running_count": row["running_count"] or 0,
            "avg_agents": round(row["avg_agents"] or 0, 2),
            "avg_ticks": round(row["avg_ticks"] or 0, 2),
        }


def get_experiment(exp_id: str) -> Optional[dict]:
    with get_db() as conn:
        row = conn.execute(
            "SELECT * FROM experiments WHERE id = ?", (exp_id,)
        ).fetchone()
        return dict(row) if row else None
