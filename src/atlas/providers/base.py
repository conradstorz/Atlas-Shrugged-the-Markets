from __future__ import annotations

from abc import ABC, abstractmethod
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
