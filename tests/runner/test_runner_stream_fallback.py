from runner.runner_stream import _fallback_priors


def test_fallback_priors_use_live_market_quote() -> None:
    priors = _fallback_priors(
        "live-market",
        {
            "condition_id": "condition-1",
            "yes_token_id": "yes-1",
            "no_token_id": "no-1",
            "winning_idx": -1,
            "end_date_iso": "2026-09-01T00:00:00Z",
            "tick_size": 0.01,
            "taker_fee_bps": 0,
        },
        0.62,
    )

    assert priors["signal_mu"] == 0.62
    assert priors["bootstrap"]["anchor_yes"] == 0.62
    assert priors["bootstrap"]["source"] == "gamma_live_quote_fallback"
    assert priors["winning_idx"] == -1


def test_fallback_priors_clamp_invalid_live_quote() -> None:
    priors = _fallback_priors(
        "live-market",
        {"condition_id": "condition-1", "tick_size": 0.01},
        2.0,
    )

    assert priors["signal_mu"] == 0.99
