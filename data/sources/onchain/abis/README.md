# Onchain ABIs (v8 scaffold — drop-in)

To activate `data/sources/onchain/`, place these JSON files here:

| File | Source | Used by |
|---|---|---|
| `exchange.json` | Polymarket Exchange `0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e` (Polygon) | `OrderFilled`, `OrdersMatched` |
| `ctf.json` | Gnosis ConditionalTokens (Polymarket-deployed) | `PositionSplit`, `PositionsMerge`, `PayoutRedemption` |
| `usdc.json` | USDC (PoS) `0x2791bca1f2de4661ed88a30c99a7a9449aa84174` | `Transfer` (for collateral flow) |

Both Polymarket Exchange and ConditionalTokens ABIs can be pulled
from PolygonScan with `gh-cli`-style:

```bash
curl -s "https://api.polygonscan.com/api?module=contract&action=getabi&address=0x4bfb41d5b3570defd03c39a9a4d8de6bd8b8982e&apikey=$POLYGONSCAN_API_KEY" \
  | jq -r '.result' > exchange.json
```

Once these files exist, `data/sources/onchain/decoder.py` will load
each ABI via `eth_abi.codec.ABICodec`. See `puller.py` docstring for
the full activation checklist.
