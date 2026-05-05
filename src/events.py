from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Dict, Tuple

from web3 import Web3


# Event signature topics from README
TOPIC_ORDER_FILLED = "0xd0a08e8c493f9c94f29311604c9de1b4e8c8d4c06bd0c789af57f2d65bfec0f6"
TOPIC_ORDERS_MATCHED = "0x63bf4d16b7fa898ef4c4b2b6d90fd201e9c56313b65638af6088d149d2ce956c"


# Minimal ABIs for decoding
ORDER_FILLED_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "orderHash", "type": "bytes32"},
        {"indexed": True, "name": "maker", "type": "address"},
        {"indexed": True, "name": "taker", "type": "address"},
        {"indexed": False, "name": "makerAssetId", "type": "uint256"},
        {"indexed": False, "name": "takerAssetId", "type": "uint256"},
        {"indexed": False, "name": "makerAmountFilled", "type": "uint256"},
        {"indexed": False, "name": "takerAmountFilled", "type": "uint256"},
        {"indexed": False, "name": "fee", "type": "uint256"},
    ],
    "name": "OrderFilled",
    "type": "event",
}

ORDERS_MATCHED_ABI = {
    "anonymous": False,
    "inputs": [
        {"indexed": True, "name": "takerOrderHash", "type": "bytes32"},
        {"indexed": True, "name": "takerOrderMaker", "type": "address"},
        {"indexed": False, "name": "makerAssetId", "type": "uint256"},
        {"indexed": False, "name": "takerAssetId", "type": "uint256"},
        {"indexed": False, "name": "makerAmountFilled", "type": "uint256"},
        {"indexed": False, "name": "takerAmountFilled", "type": "uint256"},
    ],
    "name": "OrdersMatched",
    "type": "event",
}


def _decode_event(web3: Web3, event_abi: Dict[str, Any], log: Dict[str, Any]) -> Dict[str, Any]:
    # Use Web3 codec to decode indexed and non-indexed params
    # Reference: web3 v6 get_event_data
    from web3._utils.events import get_event_data

    return get_event_data(web3.codec, event_abi, log)["args"]


def decode_order_filled(web3: Web3, log: Dict[str, Any]) -> Tuple[str, str, str, str, str, str, str, str]:
    args = _decode_event(web3, ORDER_FILLED_ABI, log)
    order_hash = Web3.to_hex(args["orderHash"]).lower()
    maker = Web3.to_checksum_address(args["maker"]) if args["maker"] else "0x0000000000000000000000000000000000000000"
    taker = Web3.to_checksum_address(args["taker"]) if args["taker"] else "0x0000000000000000000000000000000000000000"
    maker_asset_id = str(int(args["makerAssetId"]))
    taker_asset_id = str(int(args["takerAssetId"]))
    maker_amount_filled = str(int(args["makerAmountFilled"]))
    taker_amount_filled = str(int(args["takerAmountFilled"]))
    fee = str(int(args["fee"]))
    return (
        order_hash,
        maker.lower(),
        taker.lower(),
        maker_asset_id,
        taker_asset_id,
        maker_amount_filled,
        taker_amount_filled,
        fee,
    )


def decode_orders_matched(web3: Web3, log: Dict[str, Any]) -> Tuple[str, str, str, str, str, str]:
    args = _decode_event(web3, ORDERS_MATCHED_ABI, log)
    taker_order_hash = Web3.to_hex(args["takerOrderHash"]).lower()
    taker_order_maker = Web3.to_checksum_address(args["takerOrderMaker"]) if args["takerOrderMaker"] else "0x0000000000000000000000000000000000000000"
    maker_asset_id = str(int(args["makerAssetId"]))
    taker_asset_id = str(int(args["takerAssetId"]))
    maker_amount_filled = str(int(args["makerAmountFilled"]))
    taker_amount_filled = str(int(args["takerAmountFilled"]))
    return (
        taker_order_hash,
        taker_order_maker.lower(),
        maker_asset_id,
        taker_asset_id,
        maker_amount_filled,
        taker_amount_filled,
    )
