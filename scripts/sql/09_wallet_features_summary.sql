-- Descriptive stats on the calibrated wallet population for a target market.
--
-- Run with: clickhouse client < scripts/sql/09_wallet_features_summary.sql

SELECT
    target_market_id,
    count()                                  AS n_wallets,
    round(min(capital_usd), 0)               AS cap_min,
    round(quantile(0.25)(capital_usd), 0)    AS cap_q25,
    round(quantile(0.50)(capital_usd), 0)    AS cap_med,
    round(quantile(0.75)(capital_usd), 0)    AS cap_q75,
    round(max(capital_usd), 0)               AS cap_max,
    round(avg(maker_ratio), 3)               AS avg_maker_ratio,
    round(avg(past_accuracy), 3)             AS avg_past_acc,
    round(avg(asset_diversity), 1)           AS avg_diversity
FROM polymetl.wallet_features FINAL
GROUP BY target_market_id
ORDER BY target_market_id
FORMAT PrettyCompact;
