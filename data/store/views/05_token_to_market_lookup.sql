-- Reverse-lookup: given an on-chain ERC1155 outcome token id (the
-- maker_asset_id / taker_asset_id seen in OrderFilled events), find
-- the human-readable Polymarket market it belongs to.
--
-- Replace the literal in WHERE with the asset id of interest.
--
-- Run with: clickhouse client < scripts/sql/05_token_to_market_lookup.sql

SELECT
    slug,
    question,
    outcomes,
    indexOf(clob_token_ids, '69324317355037271422943965141382095011871956039434394956830818206664869608517')
                              AS outcome_index,
    arrayElement(
        outcomes,
        indexOf(clob_token_ids, '69324317355037271422943965141382095011871956039434394956830818206664869608517')
    )                         AS matching_outcome,
    `closed`,
    round(volume, 0)          AS volume_usd
FROM polymetl.markets FINAL
WHERE has(clob_token_ids, '69324317355037271422943965141382095011871956039434394956830818206664869608517')
FORMAT Vertical;
