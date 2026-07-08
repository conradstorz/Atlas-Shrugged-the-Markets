CREATE TABLE IF NOT EXISTS etf (
    symbol TEXT PRIMARY KEY,
    description TEXT NOT NULL,
    fund_type TEXT,
    category TEXT,
    select_list TEXT,
    top_ten_holdings TEXT,
    gross_expense_ratio TEXT,
    information_technology_exposure TEXT,
    source TEXT
);

CREATE TABLE IF NOT EXISTS etf_holding (
    etf_symbol TEXT NOT NULL REFERENCES etf(symbol),
    holding_symbol TEXT NOT NULL,
    holding_name TEXT,
    rank INTEGER NOT NULL,
    weight REAL,
    source TEXT NOT NULL DEFAULT 'seed_top_ten',
    PRIMARY KEY (etf_symbol, holding_symbol)
);

CREATE TABLE IF NOT EXISTS etf_score (
    symbol TEXT PRIMARY KEY REFERENCES etf(symbol),
    role TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    ai_score INTEGER NOT NULL,
    resilience_score INTEGER NOT NULL,
    cost_score INTEGER NOT NULL,
    diversification_score INTEGER NOT NULL,
    explanation TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS portfolio (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    notes TEXT
);

CREATE TABLE IF NOT EXISTS portfolio_position (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    portfolio_id INTEGER NOT NULL REFERENCES portfolio(id) ON DELETE CASCADE,
    symbol TEXT NOT NULL,
    description TEXT,
    asset_type TEXT NOT NULL DEFAULT 'ETF',
    market_value REAL NOT NULL,
    notes TEXT,
    UNIQUE (portfolio_id, symbol)
);

CREATE TABLE IF NOT EXISTS decision_journal_entry (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    symbol TEXT NOT NULL,
    entry_date TEXT NOT NULL DEFAULT CURRENT_DATE,
    decision TEXT NOT NULL,
    thesis TEXT NOT NULL,
    confidence INTEGER CHECK (confidence BETWEEN 0 AND 100),
    max_allocation_percent REAL,
    change_mind_conditions TEXT,
    notes TEXT
);
