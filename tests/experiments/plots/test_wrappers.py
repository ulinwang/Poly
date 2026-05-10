"""Verify the thin per-figure wrapper modules expose the expected
`render` callable (aliased to a function in experiments.plots._shared)."""
from __future__ import annotations

import unittest

from experiments.plots import (
    market_landscape, wallet_population, price_curve,
    pnl_distribution, role_quartiles, action_mix, _shared,
)


class PlotWrapperTests(unittest.TestCase):
    def test_market_landscape_render_is_shared_alias(self):
        self.assertIs(market_landscape.render, _shared.fig1_market_landscape)

    def test_wallet_population_render_is_shared_alias(self):
        self.assertIs(wallet_population.render, _shared.fig2_wallet_population)

    def test_price_curve_render_is_shared_alias(self):
        self.assertIs(price_curve.render, _shared.fig3_price_path)

    def test_role_quartiles_exposes_two_renders(self):
        self.assertIs(role_quartiles.render, _shared.fig4_serd_roi)
        self.assertIs(role_quartiles.render_vs_baseline,
                       _shared.fig5_serd_vs_baseline)

    def test_pnl_distribution_render_is_shared_alias(self):
        self.assertIs(pnl_distribution.render, _shared.fig5_serd_vs_baseline)

    def test_action_mix_render_is_shared_alias(self):
        self.assertIs(action_mix.render, _shared.fig6_action_mix)


if __name__ == "__main__":
    unittest.main()
