"""Tests for experiments router and database persistence."""
from __future__ import annotations

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
import time
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

import database as db_module
from routers.experiments import _RUNS, _RUNS_LOCK, _make_emitter, RunHandle


@pytest.fixture(autouse=True)
def clean_runs():
    with _RUNS_LOCK:
        _RUNS.clear()
    yield
    with _RUNS_LOCK:
        _RUNS.clear()


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test_experiments.db")
    with _RUNS_LOCK:
        _RUNS.clear()
    from server_v2 import app
    return TestClient(app)


# ---------------------------------------------------------------------------
# Database layer tests
# ---------------------------------------------------------------------------

def test_schema_has_new_columns(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    with db_module.get_db() as conn:
        cur = conn.execute("PRAGMA table_info(experiments)")
        cols = {row["name"] for row in cur.fetchall()}
    assert "final_yes_mid" in cols
    assert "total_fills" in cols
    assert "total_actions" in cols
    assert "avg_tick_time_ms" in cols


def test_save_experiment_with_metrics(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    db_module.save_experiment({
        "id": "m1",
        "slug": "btc",
        "n_agents": 10,
        "n_ticks": 5,
        "persona_set": "archetype",
        "status": "running",
        "started_at": time.time(),
    })
    db_module.save_experiment({
        "id": "m1",
        "status": "completed",
        "finished_at": time.time(),
        "result_summary": json.dumps({"foo": "bar"}),
        "final_yes_mid": 0.55,
        "total_fills": 10,
        "total_actions": 20,
        "avg_tick_time_ms": 400.0,
    })
    exp = db_module.get_experiment("m1")
    assert exp is not None
    assert exp["status"] == "completed"
    assert exp["final_yes_mid"] == 0.55
    assert exp["total_fills"] == 10
    assert exp["total_actions"] == 20
    assert exp["avg_tick_time_ms"] == 400.0


def test_get_experiments_filtered(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    for i in range(3):
        db_module.save_experiment({
            "id": f"e{i}",
            "slug": "btc" if i < 2 else "eth",
            "n_agents": 10,
            "n_ticks": 5,
            "persona_set": "archetype",
            "status": "running" if i == 0 else "completed",
            "started_at": time.time(),
        })
    exps, total = db_module.get_experiments_filtered(limit=10, offset=0)
    assert total == 3
    exps, total = db_module.get_experiments_filtered(status="running")
    assert total == 1 and exps[0]["id"] == "e0"
    exps, total = db_module.get_experiments_filtered(slug="btc")
    assert total == 2
    exps, total = db_module.get_experiments_filtered(slug="btc", limit=1, offset=1)
    assert len(exps) == 1


def test_search_experiments(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    db_module.save_experiment({
        "id": "s1", "slug": "bitcoin", "n_agents": 10, "n_ticks": 5,
        "persona_set": "archetype", "status": "completed", "started_at": time.time(),
    })
    db_module.save_experiment({
        "id": "s2", "slug": "ethereum", "n_agents": 10, "n_ticks": 5,
        "persona_set": "archetype", "status": "completed", "started_at": time.time(),
    })
    res = db_module.search_experiments("bit")
    assert len(res) == 1 and res[0]["slug"] == "bitcoin"


def test_get_experiment_stats(tmp_path, monkeypatch):
    monkeypatch.setattr(db_module, "DB_PATH", tmp_path / "test.db")
    for i, st in enumerate(["running", "completed", "completed"]):
        db_module.save_experiment({
            "id": f"st{i}", "slug": f"m{i}", "n_agents": 10 + i, "n_ticks": 20,
            "persona_set": "archetype", "status": st, "started_at": time.time(),
        })
    stats = db_module.get_experiment_stats()
    assert stats["total_runs"] == 3
    assert stats["running_count"] == 1
    assert stats["avg_agents"] == 11.0
    assert stats["avg_ticks"] == 20.0


# ---------------------------------------------------------------------------
# Router / API tests
# ---------------------------------------------------------------------------

def test_list_experiments_pagination(client):
    for i in range(5):
        db_module.save_experiment({
            "id": f"api{i}", "slug": f"m{i}", "n_agents": 10, "n_ticks": 5,
            "persona_set": "archetype", "status": "completed", "started_at": time.time(),
        })
    r = client.get("/api/v1/experiments?limit=2&offset=1")
    assert r.status_code == 200
    data = r.json()
    assert len(data["experiments"]) == 2
    assert data["total"] == 5
    assert data["limit"] == 2
    assert data["offset"] == 1


def test_list_experiments_filtering(client):
    db_module.save_experiment({
        "id": "f1", "slug": "btc", "n_agents": 10, "n_ticks": 5,
        "persona_set": "archetype", "status": "running", "started_at": time.time(),
    })
    db_module.save_experiment({
        "id": "f2", "slug": "eth", "n_agents": 10, "n_ticks": 5,
        "persona_set": "archetype", "status": "completed", "started_at": time.time(),
    })
    r = client.get("/api/v1/experiments?status=running")
    assert r.status_code == 200
    assert len(r.json()["experiments"]) == 1
    r = client.get("/api/v1/experiments?slug=btc")
    assert r.status_code == 200
    assert len(r.json()["experiments"]) == 1


def test_search_endpoint(client):
    db_module.save_experiment({
        "id": "se1", "slug": "bitcoin", "n_agents": 10, "n_ticks": 5,
        "persona_set": "archetype", "status": "completed", "started_at": time.time(),
    })
    r = client.get("/api/v1/experiments/search?q=bit")
    assert r.status_code == 200
    data = r.json()
    assert len(data["experiments"]) == 1
    assert data["experiments"][0]["slug"] == "bitcoin"
    r = client.get("/api/v1/experiments/search?q=")
    assert r.status_code == 200
    assert r.json()["experiments"] == []


def test_stats_endpoint(client):
    db_module.save_experiment({
        "id": "stat1", "slug": "m1", "n_agents": 10, "n_ticks": 5,
        "persona_set": "archetype", "status": "running", "started_at": time.time(),
    })
    r = client.get("/api/v1/experiments/stats")
    assert r.status_code == 200
    data = r.json()
    assert data["total_runs"] == 1
    assert data["running_count"] == 1


def test_create_experiment_mocked(client):
    with patch("routers.experiments._spawn_run") as mock_spawn:
        r = client.post("/api/v1/experiments", json={
            "slug": "btc", "n_agents": 10, "n_ticks": 5, "persona_set": "archetype",
        })
        assert r.status_code == 200
        run_id = r.json()["run_id"]
        exp = db_module.get_experiment(run_id)
        assert exp is not None
        assert exp["slug"] == "btc"
        assert exp["status"] == "running"
        with _RUNS_LOCK:
            assert run_id in _RUNS
        mock_spawn.assert_called_once()


def test_cancel_experiment(client):
    with patch("routers.experiments._spawn_run"):
        r = client.post("/api/v1/experiments", json={
            "slug": "btc", "n_agents": 10, "n_ticks": 5, "persona_set": "archetype",
        })
        run_id = r.json()["run_id"]
    r = client.post(f"/api/v1/experiments/{run_id}/cancel")
    assert r.status_code == 200
    exp = db_module.get_experiment(run_id)
    assert exp["status"] == "cancelled"


def test_read_experiment_db_and_memory(client):
    with patch("routers.experiments._spawn_run"):
        r = client.post("/api/v1/experiments", json={
            "slug": "btc", "n_agents": 10, "n_ticks": 5, "persona_set": "archetype",
        })
        run_id = r.json()["run_id"]
    # DB read
    r = client.get(f"/api/v1/experiments/{run_id}")
    assert r.status_code == 200
    assert r.json()["experiment"]["id"] == run_id
    # In-memory fallback: remove from DB but keep in _RUNS
    with db_module.get_db() as conn:
        conn.execute("DELETE FROM experiments WHERE id = ?", (run_id,))
    r = client.get(f"/api/v1/experiments/{run_id}")
    assert r.status_code == 200
    assert r.json()["experiment"]["id"] == run_id


# ---------------------------------------------------------------------------
# Internal unit tests
# ---------------------------------------------------------------------------

def test_emitter_accumulates_metrics():
    handle = RunHandle(run_id="r1", slug="s", n_agents=10, n_ticks=5, persona_set="a")
    emit = _make_emitter(handle)
    emit("tick_finished", {"elapsed_s": 0.5})
    emit("tick_finished", {"elapsed_s": 0.3})
    emit("settled", {"yes_mid_final": 0.55, "n_fills": 10, "n_actions": 20})
    assert handle.tick_count == 2
    assert handle.tick_elapsed_s_total == 0.8
    assert handle.final_metrics["yes_mid_final"] == 0.55
