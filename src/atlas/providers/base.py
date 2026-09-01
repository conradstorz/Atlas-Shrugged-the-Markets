from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping


class ResearchDataProvider(ABC):
    """Interface for public research data providers."""

    @abstractmethod
    def iter_funds(self) -> Iterable[Mapping[str, object]]:
        """Yield public fund metadata records."""


class PortfolioImportProvider(ABC):
    """Interface for private portfolio import providers."""

    @abstractmethod
    def import_file(self, path: Path) -> Iterable[Mapping[str, object]]:
        """Yield private portfolio position records from a local file."""


@dataclass(frozen=True)
class FundHolding:
    holding_symbol: str
    holding_name: str | None
    weight: float          # percent, e.g. 6.83


class FundHoldingsProvider(ABC):
    """Interface for a source of one fund's holdings with weights."""

    @abstractmethod
    def iter_holdings(self) -> Iterable[FundHolding]:
        """Yield the fund's holdings."""
