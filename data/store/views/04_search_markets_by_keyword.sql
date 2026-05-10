-- Find markets whose question or description contains a keyword.
-- Edit the literal in the WHERE clause to change the search term.
--
-- Run with: clickhouse client < scripts/sql/04_search_markets_by_keyword.sql

SELECT
    slug,
    left(question, 80)        AS question,
    `closed`,
    round(volume, 0)          AS volume_usd,
    outcome_prices,
    end_date
FROM polymetl.markets FINAL
WHERE question ILIKE '%AI%'
   OR question ILIKE '%GPT%'
   OR question ILIKE '%Claude%'
   OR question ILIKE '%OpenAI%'
   OR question ILIKE '%Anthropic%'
ORDER BY volume DESC
LIMIT 50
FORMAT PrettyCompact;
