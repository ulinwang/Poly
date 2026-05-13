"""Smoke tests for the v12 live demo FastAPI app. No network, no LLM."""
from __future__ import annotations

import unittest
from unittest import mock

from fastapi.testclient import TestClient

from webapp import server


class StaticAssetsTest(unittest.TestCase):
    def test_index_html_served(self):
        client = TestClient(server.app)
        r = client.get("/")
        self.assertEqual(r.status_code, 200)
        self.assertIn("PolyMetl Live", r.text)

    def test_app_js_served(self):
        client = TestClient(server.app)
        r = client.get("/static/app.js")
        self.assertEqual(r.status_code, 200)
        self.assertIn("createApp", r.text)

    def test_style_css_served(self):
        client = TestClient(server.app)
        r = client.get("/static/style.css")
        self.assertEqual(r.status_code, 200)
        self.assertIn("--accent", r.text)


class MarketsEndpointTest(unittest.TestCase):
    def test_returns_rows(self):
        fake_ch = mock.Mock()
        fake_ch.client.execute.return_value = [
            ("slug-a", "Will A?", "0xCID_A", 1234.0, 0, "2026-01-01"),
            ("slug-b", "Will B?", "0xCID_B", 99.0, None, None),
        ]
        with mock.patch.object(server, "get_ch", return_value=fake_ch):
            client = TestClient(server.app)
            r = client.get("/api/markets?q=foo&limit=10")
        self.assertEqual(r.status_code, 200)
        body = r.json()
        self.assertEqual(len(body["markets"]), 2)
        self.assertFalse(body["markets"][0]["is_live"])
        self.assertTrue(body["markets"][1]["is_live"])

    def test_live_only_filter(self):
        fake_ch = mock.Mock()
        fake_ch.client.execute.return_value = [
            ("slug-a", "Will A?", "0xCID_A", 1234.0, 0, "2026-01-01"),
            ("slug-b", "Will B?", "0xCID_B", 99.0, None, None),
        ]
        with mock.patch.object(server, "get_ch", return_value=fake_ch):
            client = TestClient(server.app)
            r = client.get("/api/markets?live_only=1")
        self.assertEqual(r.status_code, 200)
        rows = r.json()["markets"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["slug"], "slug-b")


class RunLifecycleTest(unittest.TestCase):
    def test_post_and_status(self):
        captured = {}

        def fake_spawn(handle):
            captured["handle"] = handle
            # Don't start the thread — just record the handle.

        with mock.patch.object(server, "_spawn_run", side_effect=fake_spawn):
            client = TestClient(server.app)
            r = client.post("/api/runs", json={
                "slug": "fake-slug", "n_agents": 5, "n_ticks": 2,
                "persona_set": "archetype",
            })
            self.assertEqual(r.status_code, 200)
            rid = r.json()["run_id"]
            self.assertEqual(len(rid), 12)
            s = client.get(f"/api/runs/{rid}")
            self.assertEqual(s.status_code, 200)
            self.assertEqual(s.json()["slug"], "fake-slug")
            self.assertEqual(s.json()["n_agents"], 5)

    def test_rejects_unknown_persona(self):
        client = TestClient(server.app)
        r = client.post("/api/runs", json={
            "slug": "x", "n_agents": 3, "n_ticks": 2,
            "persona_set": "garbage",
        })
        self.assertEqual(r.status_code, 400)

    def test_status_404_for_unknown(self):
        client = TestClient(server.app)
        r = client.get("/api/runs/deadbeef")
        self.assertEqual(r.status_code, 404)

    def test_cancel_unknown(self):
        client = TestClient(server.app)
        r = client.post("/api/runs/deadbeef/cancel")
        self.assertEqual(r.status_code, 404)


if __name__ == "__main__":
    unittest.main()
