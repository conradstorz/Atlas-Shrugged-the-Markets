from __future__ import annotations

import ast
import inspect
from pathlib import Path

from atlas.providers import holdings_file, portfolio_files, seed_universe
from atlas.providers.base import FundHoldingsProvider, PortfolioImportProvider, ResearchDataProvider
from atlas.providers.holdings_file import HoldingsFileProvider
from atlas.providers.portfolio_files import PortfolioCsvProvider, SchwabPositionsProvider
from atlas.providers.seed_universe import SeedUniverseProvider

SEED = Path("data/atlas_seed_universe.csv")
SAMPLE_PORTFOLIO = Path("examples/sample_portfolio.csv")
SCHWAB_SAMPLE = Path("tests/fixtures/schwab_positions_sample.csv")
SCHWAB_MULTI = Path("tests/fixtures/schwab_positions_multi_account.csv")


# --- interface conformance -------------------------------------------------


def test_holdings_file_provider_is_a_fund_holdings_provider() -> None:
    assert issubclass(HoldingsFileProvider, FundHoldingsProvider)


def test_seed_universe_provider_is_a_research_data_provider() -> None:
    assert issubclass(SeedUniverseProvider, ResearchDataProvider)
    assert isinstance(SeedUniverseProvider(SEED), ResearchDataProvider)


def test_portfolio_providers_are_portfolio_import_providers() -> None:
    assert issubclass(SchwabPositionsProvider, PortfolioImportProvider)
    assert issubclass(PortfolioCsvProvider, PortfolioImportProvider)
    assert isinstance(SchwabPositionsProvider(), PortfolioImportProvider)
    assert isinstance(PortfolioCsvProvider(), PortfolioImportProvider)


# --- boundary guard: providers are pure parsers -----------------------------


def test_provider_modules_do_not_import_sqlite3() -> None:
    for module in (holdings_file, portfolio_files, seed_universe):
        tree = ast.parse(inspect.getsource(module))
        imported_names = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.Import)
            for alias in node.names
        } | {
            node.module
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
        }
        assert "sqlite3" not in imported_names
        assert not any(name and name.startswith("atlas.db") for name in imported_names)


# --- SeedUniverseProvider ----------------------------------------------------


def test_seed_universe_provider_yields_105_records() -> None:
    records = list(SeedUniverseProvider(SEED).iter_funds())
    assert len(records) == 105


def test_seed_universe_provider_spot_check_divb() -> None:
    records = {r["symbol"]: r for r in SeedUniverseProvider(SEED).iter_funds()}
    divb = records["DIVB"]
    assert divb["description"] == "iShares Core Dividend ETF"
    assert divb["fund_type"] == "ETF"
    assert divb["category"] == "Total Market Dividend-focused"
    assert divb["select_list"] == "Yes"
    assert divb["gross_expense_ratio"] == "0.05%"
    assert divb["information_technology_exposure"] == "18.32%"
    assert divb["source"] == "Uploaded ETF Select List"
    assert divb["holding_symbols"] == [
        "ADP", "IBM", "ACN", "JPM", "PAYX", "JNJ", "HPQ", "XOM", "ABBV", "CTSH",
    ]


# --- SchwabPositionsProvider --------------------------------------------------


def test_schwab_positions_provider_yields_rows_with_cash_mapped_and_total_skipped() -> None:
    rows = list(SchwabPositionsProvider().import_file(SCHWAB_SAMPLE))
    symbols = [r["symbol"] for r in rows]
    assert symbols == ["NVDA", "GILD", "SCHD", "FSELX", "CASH"]
    assert "Positions Total" not in symbols

    by_symbol = {r["symbol"]: r for r in rows}
    assert by_symbol["NVDA"]["asset_type"] == "equity"
    assert by_symbol["NVDA"]["market_value"] == 10410.12
    assert by_symbol["CASH"]["asset_type"] == "cash"
    assert by_symbol["CASH"]["market_value"] == 27.81


def test_schwab_positions_provider_yields_duplicate_symbols_unsummed() -> None:
    rows = list(SchwabPositionsProvider().import_file(SCHWAB_MULTI))
    nvda_rows = [r for r in rows if r["symbol"] == "NVDA"]
    # One row per account section, not summed: accumulation is the loader's job.
    assert len(nvda_rows) == 2
    assert {r["market_value"] for r in nvda_rows} == {10000.0, 7000.0}


# --- PortfolioCsvProvider -----------------------------------------------------


def test_portfolio_csv_provider_yields_expected_records() -> None:
    rows = list(PortfolioCsvProvider().import_file(SAMPLE_PORTFOLIO))
    by_symbol = {r["symbol"]: r for r in rows}
    assert set(by_symbol) == {"SCHB", "SCHD", "RSP", "SGOV"}
    assert by_symbol["SCHB"]["market_value"] == 50000.0
    assert by_symbol["SCHB"]["asset_type"] == "etf"
    assert by_symbol["SCHB"]["description"] == "Schwab U.S. Broad Market ETF"
