from __future__ import annotations

import unittest

from src.sim import serd


class NetworkConstructionTest(unittest.TestCase):
    def test_net_flow_collapses_symmetric_pairs(self):
        edges = {(1, 2): 100.0, (2, 1): 30.0}  # net 70 from 1 → 2
        out = serd.net_flow_edges(edges)
        self.assertEqual(out, {(1, 2): 70.0})

    def test_net_flow_drops_zero_residual(self):
        edges = {(1, 2): 50.0, (2, 1): 50.0}
        out = serd.net_flow_edges(edges)
        self.assertEqual(out, {})

    def test_net_flow_keeps_one_sided(self):
        edges = {(1, 2): 100.0}
        self.assertEqual(serd.net_flow_edges(edges), {(1, 2): 100.0})

    def test_node_strengths_basic(self):
        edges = {(1, 2): 100.0, (3, 2): 50.0, (1, 3): 20.0}
        s = serd.node_strengths(edges, [1, 2, 3])
        self.assertAlmostEqual(s[1]["in"], 100.0 + 20.0)
        self.assertAlmostEqual(s[1]["out"], 0.0)
        self.assertAlmostEqual(s[2]["in"], 0.0)
        self.assertAlmostEqual(s[2]["out"], 100.0 + 50.0)
        self.assertAlmostEqual(s[3]["in"], 50.0)
        self.assertAlmostEqual(s[3]["out"], 20.0)
        # Apex agent (1) has very high in/out ratio (since out=0 → ratio≈huge)
        self.assertGreater(s[1]["ratio"], s[3]["ratio"])
        # Prey agent (2) has zero in/out → ratio 0
        self.assertEqual(s[2]["ratio"], 0.0)


class RoleAssignmentTest(unittest.TestCase):
    def test_quartile_4_agents(self):
        # Construct strengths with explicit ratios 1.0, 2.0, 3.0, 4.0
        strengths = {
            10: {"in": 1.0, "out": 1.0, "ratio": 1.0},
            20: {"in": 2.0, "out": 1.0, "ratio": 2.0},
            30: {"in": 3.0, "out": 1.0, "ratio": 3.0},
            40: {"in": 4.0, "out": 1.0, "ratio": 4.0},
        }
        out = serd.assign_quartile_roles(strengths)
        # Apex = highest ratio
        self.assertEqual(out[40], "ApexPredator")
        self.assertEqual(out[10], "Prey")
        self.assertIn(out[20], {"LowerMeso", "UpperMeso"})
        self.assertIn(out[30], {"LowerMeso", "UpperMeso"})

    def test_quartile_8_agents_balanced(self):
        # 8 agents → 2 in each role
        strengths = {
            i: {"in": float(i), "out": 1.0, "ratio": float(i)}
            for i in range(1, 9)
        }
        out = serd.assign_quartile_roles(strengths)
        from collections import Counter
        c = Counter(out.values())
        self.assertEqual(c["ApexPredator"], 2)
        self.assertEqual(c["UpperMeso"], 2)
        self.assertEqual(c["LowerMeso"], 2)
        self.assertEqual(c["Prey"], 2)
        # Top two by ratio (7, 8) are Apex
        self.assertEqual(out[8], "ApexPredator")
        self.assertEqual(out[7], "ApexPredator")
        # Bottom two (1, 2) are Prey
        self.assertEqual(out[1], "Prey")
        self.assertEqual(out[2], "Prey")

    def test_empty_returns_empty(self):
        self.assertEqual(serd.assign_quartile_roles({}), {})


class GroupAggregationTest(unittest.TestCase):
    def test_roi_by_role_means(self):
        role_of = {1: "ApexPredator", 2: "Prey", 3: "ApexPredator"}
        roi_of = {
            1: {"roi": 0.20, "capital": 1000, "pnl": 200, "final_value": 1200},
            2: {"roi": -0.10, "capital": 500, "pnl": -50, "final_value": 450},
            3: {"roi": 0.10, "capital": 1000, "pnl": 100, "final_value": 1100},
        }
        out = serd.roi_by_role(role_of, roi_of)
        self.assertAlmostEqual(out["ApexPredator"]["mean_roi"], 0.15)
        self.assertEqual(out["ApexPredator"]["n"], 2)
        self.assertAlmostEqual(out["Prey"]["mean_roi"], -0.10)
        # vol_share: Apex has 2000 of 2500 total = 0.8
        self.assertAlmostEqual(out["ApexPredator"]["vol_share"], 0.8)


class MonotonicityTest(unittest.TestCase):
    def test_paper_signature_pattern(self):
        roi_role = {
            "ApexPredator": {"n": 2, "mean_roi": 0.15, "vol_share": 0.5},
            "UpperMeso":    {"n": 2, "mean_roi": 0.10, "vol_share": 0.2},
            "LowerMeso":    {"n": 2, "mean_roi": 0.05, "vol_share": 0.2},
            "Prey":         {"n": 2, "mean_roi": -0.05, "vol_share": 0.1},
        }
        self.assertTrue(serd.monotonic_descending(roi_role))
        self.assertAlmostEqual(serd.delta_roi(roi_role), 0.20)

    def test_non_monotonic(self):
        roi_role = {
            "ApexPredator": {"n": 1, "mean_roi": 0.1, "vol_share": 1.0},
            "UpperMeso":    {"n": 1, "mean_roi": 0.5, "vol_share": 0.0},
            "LowerMeso":    {"n": 1, "mean_roi": 0.05, "vol_share": 0.0},
            "Prey":         {"n": 1, "mean_roi": 0.0, "vol_share": 0.0},
        }
        self.assertFalse(serd.monotonic_descending(roi_role))

    def test_empty_returns_zero(self):
        empty = {r: {"n": 0, "mean_roi": 0, "vol_share": 0} for r in serd.ROLES}
        self.assertEqual(serd.delta_roi(empty), 0.0)


class KmeansBaselineTest(unittest.TestCase):
    def test_kmeans_partitions_into_two_clusters(self):
        # Two clearly separated agents should land in different clusters
        feats = {
            10: {"tx_freq": 100, "maker_ratio": 0.9, "avg_pos": 100.0,
                 "asset_diversity": 1},
            20: {"tx_freq": 5,   "maker_ratio": 0.1, "avg_pos": 10.0,
                 "asset_diversity": 1},
        }
        out = serd._kmeans_2(feats)
        self.assertEqual(len(out), 2)
        self.assertNotEqual(out[10], out[20])

    def test_kmeans_empty(self):
        self.assertEqual(serd._kmeans_2({}), {})

    def test_kmeans_single(self):
        feats = {1: {"tx_freq": 1, "maker_ratio": 0, "avg_pos": 0,
                     "asset_diversity": 1}}
        out = serd._kmeans_2(feats)
        self.assertEqual(out, {1: 0})


if __name__ == "__main__":
    unittest.main()
