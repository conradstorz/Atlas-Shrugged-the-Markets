from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Asset:
    symbol: str
    name: str
    asset_type: str


@dataclass(frozen=True)
class Fund(Asset):
    sponsor: str | None = None
    expense_ratio: float | None = None


@dataclass(frozen=True)
class Company(Asset):
    sector: str | None = None
    industry: str | None = None
