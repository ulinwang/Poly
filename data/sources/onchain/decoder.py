"""v8 — ABI-based event log decoder. SCAFFOLD ONLY.

When the abis/ JSON files are dropped in, this module will:
  - load each ABI via `eth_abi.codec.ABICodec` or web3 contract object;
  - expose `decode_log(log: dict, contract: str) -> dict` returning
    the typed event payload.

For now: stub raises NotImplementedError.
"""
from __future__ import annotations


def decode_log(log: dict, contract: str) -> dict:
    raise NotImplementedError(
        "data.sources.onchain.decoder is a v8 scaffold; "
        "drop ABI files into data/sources/onchain/abis/ first."
    )
