"""
Central Limit Order Book (CLOB) for binary outcome tokens, modeled on
Polymarket's actual matching engine.

Two independent books per market — one for YES outcome tokens, one for
NO. Each book has bids (sorted desc by price, then asc by ts) and asks
(sorted asc by price, then asc by ts). Price-time priority matching.

Conventions:
  - price ∈ [0, 1] in USDC per share
  - size in shares (1 share pays $1 if its outcome wins, $0 otherwise)
  - BUY at best ask = taking liquidity (taker)
  - SELL at best bid = taking liquidity (taker)
  - LIMIT order that does not immediately match becomes a maker resting
    on the book

Reference: this is the standard prediction-market CLOB. Polymarket
documents their engine at https://docs.polymarket.com/developers
(though we implement only the matching essentials, not full L2 depth
or per-tick book snapshots).
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Optional


_EPS = 1e-9
_WIDE_SPREAD = 0.10


@dataclass
class Order:
    order_id: int
    agent_id: int
    side: str         # 'BUY' or 'SELL'
    price: float      # 0..1
    size: float       # initial share count
    ts: int           # tick at which order was placed
    remaining: float = 0.0  # fills decrement this; 0 → fully filled

    def __post_init__(self) -> None:
        if self.remaining == 0.0:
            self.remaining = self.size


@dataclass
class Fill:
    maker_order_id: int
    taker_order_id: int
    maker_agent_id: int
    taker_agent_id: int
    maker_side: str          # the side the MAKER had been resting on
    price: float
    size: float
    ts: int


class OrderBook:
    """One side of a binary-outcome market (YES or NO token)."""

    def __init__(self, name: str = "YES", tick_size: float = 0.01) -> None:
        self.name = name
        self.tick_size = tick_size
        self._next_order_id = 1
        self.bids: list[Order] = []   # sorted desc by price, asc by ts
        self.asks: list[Order] = []   # sorted asc by price, asc by ts
        self.cancelled: set[int] = set()
        self.last_trade_price: Optional[float] = None

    # ---- helpers ----
    def _is_aligned(self, price: float) -> bool:
        """Return True iff price is a multiple of tick_size (within tol)."""
        snapped = round(price / self.tick_size) * self.tick_size
        return math.isclose(snapped, price, abs_tol=1e-9)

    # ---- inspection ----
    def best_bid(self) -> Optional[float]:
        return self.bids[0].price if self.bids else None

    def best_ask(self) -> Optional[float]:
        return self.asks[0].price if self.asks else None

    def mid(self, fallback: float = 0.5) -> float:
        b, a = self.best_bid(), self.best_ask()
        if b is not None and a is not None and (a - b) <= _WIDE_SPREAD + _EPS:
            return (b + a) / 2.0
        if self.last_trade_price is not None:
            return self.last_trade_price
        # No last trade — fall back to single-side best if exactly one
        # side has liquidity, else the explicit fallback.
        if b is not None and a is None:
            return b
        if a is not None and b is None:
            return a
        return fallback

    def depth_at(self, side: str, levels: int = 5) -> list[tuple[float, float]]:
        """Return up to `levels` price/size aggregates from one side."""
        book = self.bids if side == "BUY" else self.asks
        out: list[tuple[float, float]] = []
        for o in book:
            if not out or out[-1][0] != o.price:
                if len(out) >= levels:
                    break
                out.append((o.price, 0.0))
            out[-1] = (out[-1][0], out[-1][1] + o.remaining)
        return out

    # ---- mutation ----
    def add_limit(
        self, agent_id: int, side: str, price: float, size: float, ts: int,
    ) -> tuple[list[Fill], Order]:
        """Add a limit order. Crosses into the book and matches; any
        remainder is resting. Returns (fills_made, the_order)."""
        assert side in {"BUY", "SELL"}
        misaligned = (
            price > 0 and price < 1 and not self._is_aligned(price)
        )
        if size <= _EPS or price < 0 or price > 1 or misaligned:
            order = Order(
                order_id=self._next_order_id, agent_id=agent_id, side=side,
                price=price, size=0.0, ts=ts,
            )
            self._next_order_id += 1
            return [], order

        order = Order(
            order_id=self._next_order_id, agent_id=agent_id, side=side,
            price=price, size=size, ts=ts,
        )
        self._next_order_id += 1
        opp = self.asks if side == "BUY" else self.bids
        fills: list[Fill] = []

        while order.remaining > _EPS and opp:
            top = opp[0]
            if top.order_id in self.cancelled or top.remaining <= _EPS:
                opp.pop(0)
                continue
            crosses = (
                (side == "BUY" and order.price + _EPS >= top.price)
                or (side == "SELL" and order.price - _EPS <= top.price)
            )
            if not crosses:
                break
            qty = min(order.remaining, top.remaining)
            fills.append(Fill(
                maker_order_id=top.order_id, taker_order_id=order.order_id,
                maker_agent_id=top.agent_id, taker_agent_id=agent_id,
                maker_side=top.side, price=top.price, size=qty, ts=ts,
            ))
            order.remaining -= qty
            top.remaining -= qty
            if top.remaining <= _EPS:
                opp.pop(0)

        if fills:
            self.last_trade_price = fills[-1].price

        if order.remaining > _EPS:
            same = self.bids if side == "BUY" else self.asks
            self._insert_sorted(same, order)
        return fills, order

    def add_market(
        self, agent_id: int, side: str, size: float, ts: int,
    ) -> tuple[list[Fill], Order]:
        """Walk the book until size is consumed or the book is empty.
        Implemented as a LIMIT at best-extreme price (1 for BUY, 0 for SELL)."""
        sweep_price = 1.0 if side == "BUY" else 0.0
        return self.add_limit(agent_id, side, sweep_price, size, ts)

    def cancel(self, order_id: int) -> bool:
        # Lazy: mark as cancelled, will be skipped on next match.
        # Also remove from book immediately if found, for cleaner state.
        for book in (self.bids, self.asks):
            for i, o in enumerate(book):
                if o.order_id == order_id:
                    book.pop(i)
                    self.cancelled.add(order_id)
                    return True
        return False

    def cancel_all_for_agent(self, agent_id: int) -> int:
        n = 0
        for book in (self.bids, self.asks):
            keep = []
            for o in book:
                if o.agent_id == agent_id:
                    self.cancelled.add(o.order_id)
                    n += 1
                else:
                    keep.append(o)
            book[:] = keep
        return n

    # ---- internals ----
    def _insert_sorted(self, book: list[Order], order: Order) -> None:
        """Insert order while maintaining price-time priority. Bids:
        higher price first, FIFO at same price. Asks: lower price first."""
        if order.side == "BUY":
            # bids: desc price, asc ts
            i = 0
            while i < len(book) and (
                book[i].price > order.price
                or (book[i].price == order.price and book[i].ts <= order.ts)
            ):
                i += 1
            book.insert(i, order)
        else:
            # asks: asc price, asc ts
            i = 0
            while i < len(book) and (
                book[i].price < order.price
                or (book[i].price == order.price and book[i].ts <= order.ts)
            ):
                i += 1
            book.insert(i, order)
