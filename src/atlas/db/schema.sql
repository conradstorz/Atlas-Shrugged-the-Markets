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
    weight REAL, -- percent of fund, e.g. 6.83 means 6.83%; NULL for seed select-list rows (symbols only)
    source TEXT NOT NULL DEFAULT 'seed_top_ten',
    -- `source` is part of the key so a fund's seed select-list membership row
    -- and its imported holdings-file row for the SAME company can coexist.
    -- With the narrower (etf_symbol, holding_symbol) key, importing a partial
    -- issuer export of a fund's largest names overwrote exactly the seed rows
    -- that mattered and shrank the fund's top ten. Which of the two sources a
    -- fund's top ten is read from is decided by
    -- `atlas.analytics.overlap.TOP_TEN_CTE`, not by the storage key.
    PRIMARY KEY (etf_symbol, holding_symbol, source)
);

CREATE TABLE IF NOT EXISTS etf_score (
    symbol TEXT PRIMARY KEY REFERENCES etf(symbol),
    role TEXT NOT NULL,
    overall_score INTEGER NOT NULL,
    ai_score INTEGER NOT NULL,
    resilience_score INTEGER NOT NULL,
    cost_score INTEGER NOT NULL,
    -- NULL means "not measured": the fund has no imported holdings file
    -- covering essentially the whole fund, so its breadth is unknown and the
    -- component is excluded from overall_score rather than guessed at. 0 is a
    -- real score meaning "extremely concentrated" and is not a sentinel.
    diversification_score INTEGER,
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
