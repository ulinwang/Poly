"""Pydantic models for market endpoints."""
from __future__ import annotations

from pydantic import BaseModel, Field


class MarketRow(BaseModel):
    slug: str
    question: str
    condition_id: str
    volume: float
    is_live: bool
    end_date_iso: str | None = None
    n_holders: int | None = None
    categories: list[str] | None = None


class MarketDetail(MarketRow):
    tick_size: float = 0.01
    taker_fee_bps: float = 0.0
    description: str = ""
    yes_token_id: str = ""
    no_token_id: str = ""
    outcomes: list[str] = Field(default_factory=lambda: ["Yes", "No"])


class MarketsResponse(BaseModel):
    markets: list[MarketRow]


class MarketResponse(BaseModel):
    market: MarketDetail


class CategoriesResponse(BaseModel):
    categories: list[str]
