from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def connect(db_path: Path) -> sqlite3.Connection:
    """Open an Atlas SQLite database and ensure the schema exists."""
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))
    return conn


def _split_seed_holdings(raw: str | None) -> list[str]:
    """Parse the uploaded select-list top-ten format, e.g. |NVDA||AAPL|."""
    if not raw or raw.strip() in {"--", ""}:
        return []
    return [item.strip().upper() for item in raw.split("|") if item.strip()]


def load_seed_universe(conn: sqlite3.Connection, seed_path: Path) -> int:
    """Load the seed ETF universe CSV and parse top-ten holdings."""
    with seed_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        count = 0
        for row in reader:
            symbol = (row.get("Symbol") or "").strip().upper()
            if not symbol:
                continue
            top_ten = row.get("Top Ten Holdings", "")
            conn.execute(
                """
                INSERT INTO etf (
                    symbol, description, fund_type, category, select_list,
                    top_ten_holdings, gross_expense_ratio,
                    information_technology_exposure, source
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(symbol) DO UPDATE SET
                    description=excluded.description,
                    fund_type=excluded.fund_type,
                    category=excluded.category,
                    select_list=excluded.select_list,
                    top_ten_holdings=excluded.top_ten_holdings,
                    gross_expense_ratio=excluded.gross_expense_ratio,
                    information_technology_exposure=excluded.information_technology_exposure,
                    source=excluded.source
                """,
                (
                    symbol,
                    row.get("Description", ""),
                    row.get("Fund Type", ""),
                    row.get("ETF Select List® Category", ""),
                    row.get("ETF Select List", ""),
                    top_ten,
                    row.get("Gross Expense Ratio", ""),
                    row.get("Sector Exposure: Information Technology", ""),
                    row.get("Source", "Uploaded ETF Select List"),
                ),
            )
            conn.execute("DELETE FROM etf_holding WHERE etf_symbol = ? AND source = 'seed_top_ten'", (symbol,))
            for rank, holding_symbol in enumerate(_split_seed_holdings(top_ten), start=1):
                conn.execute(
                    """
                    INSERT INTO etf_holding (etf_symbol, holding_symbol, rank, source)
                    VALUES (?, ?, ?, 'seed_top_ten')
                    ON CONFLICT(etf_symbol, holding_symbol) DO UPDATE SET
                        rank=excluded.rank,
                        source=excluded.source
                    """,
                    (symbol, holding_symbol, rank),
                )
            count += 1
    conn.commit()
    return count


def load_portfolio_csv(conn: sqlite3.Connection, portfolio_name: str, portfolio_path: Path) -> int:
    """Import a private portfolio CSV with Symbol and Market Value columns.

    Accepted market-value column names: Market Value, Value, Amount.
    Existing positions for the same portfolio are replaced.
    """
    conn.execute(
        "INSERT INTO portfolio (name) VALUES (?) ON CONFLICT(name) DO NOTHING",
        (portfolio_name,),
    )
    portfolio_id = conn.execute("SELECT id FROM portfolio WHERE name = ?", (portfolio_name,)).fetchone()["id"]
    conn.execute("DELETE FROM portfolio_position WHERE portfolio_id = ?", (portfolio_id,))

    with portfolio_path.open("r", encoding="utf-8-sig", newline="") as csv_file:
        reader = csv.DictReader(csv_file)
        count = 0
        for row in reader:
            symbol = (row.get("Symbol") or row.get("Ticker") or "").strip().upper()
            if not symbol:
                continue
            raw_value = row.get("Market Value") or row.get("Value") or row.get("Amount") or "0"
            market_value = float(str(raw_value).replace("$", "").replace(",", "").strip() or 0)
            conn.execute(
                """
                INSERT INTO portfolio_position (
                    portfolio_id, symbol, description, asset_type, market_value, notes
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    portfolio_id,
                    symbol,
                    row.get("Description", ""),
                    row.get("Asset Type", "ETF"),
                    market_value,
                    row.get("Notes", ""),
                ),
            )
            count += 1
    conn.commit()
    return count
