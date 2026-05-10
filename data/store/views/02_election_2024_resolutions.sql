-- 2024 US Presidential election: which markets resolved YES vs NO,
-- ordered by trading volume.
--
-- Final outcome encoding for resolved markets:
--   outcome_prices = [1, 0]  → YES side won
--   outcome_prices = [0, 1]  → NO side won
--
-- Run with: clickhouse client < scripts/sql/02_election_2024_resolutions.sql

SELECT
    slug,
    left(question, 75) AS question,
    round(volume, 0)   AS volume_usd,
    outcome_prices,
    multiIf(
        outcome_prices = [1.0, 0.0], 'YES_won',
        outcome_prices = [0.0, 1.0], 'NO_won',
        'unresolved_or_partial'
    )                  AS result
FROM polymetl.markets FINAL
WHERE `closed` = 1
  AND (
      question ILIKE '%2024%election%'
      OR question ILIKE '%2024 us presidential%'
  )
ORDER BY volume DESC
LIMIT 30
FORMAT PrettyCompact;
