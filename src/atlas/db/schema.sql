CREATE TABLE IF NOT EXISTS asset (
    symbol      TEXT PRIMARY KEY,
    name        TEXT,                          -- NULL allowed for stub rows created by holdings import
    asset_type  TEXT NOT NULL CHECK (asset_type IN ('fund', 'company'))
);

CREATE TABLE IF NOT EXISTS fund (
    symbol                  TEXT PRIMARY KEY REFERENCES asset(symbol),
    description             TEXT NOT NULL,
    fund_type               TEXT,
    category                TEXT,
    select_list             TEXT,
    gross_expense_ratio     TEXT,
    information_technology_exposure TEXT,
    source                  TEXT               -- NULL = stub created by import-holdings; the CLI phantom-fund warning keys off this
);

CREATE TABLE IF NOT EXISTS company (
    symbol  TEXT PRIMARY KEY REFERENCES asset(symbol)
    -- no attributes yet; exists so v0.9 themes/sector have an anchor
);

CREATE TABLE IF NOT EXISTS theme (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL UNIQUE,
    description TEXT
    -- empty in v0.8; v0.9 fills it and adds theme_link
);

CREATE TABLE IF NOT EXISTS fund_holding (
    fund_symbol     TEXT NOT NULL REFERENCES fund(symbol),
    holding_symbol  TEXT NOT NULL REFERENCES asset(symbol),
    holding_name    TEXT,
    rank            INTEGER NOT NULL,
    weight          REAL, -- percent of fund, e.g. 6.83 means 6.83%; NULL for seed select-list rows (symbols only)
    source          TEXT NOT NULL DEFAULT 'seed_top_ten',
    -- `source` is part of the key so a fund's seed select-list membership row
    -- and its imported holdings-file row for the SAME company can coexist.
    -- Which of the two sources a fund's top ten is read from is decided by
    -- `atlas.analytics.overlap.TOP_TEN_CTE`, not by the storage key.
    PRIMARY KEY (fund_symbol, holding_symbol, source)
);

CREATE TABLE IF NOT EXISTS fund_score (
    symbol TEXT PRIMARY KEY REFERENCES fund(symbol),
    -- `role` and `ai_score` are keyword heuristics over the fund's description,
    -- so they are always available and stay NOT NULL. Every other score is
    -- nullable, and NULL always means the same thing: not measured, therefore
    -- excluded from overall_score rather than substituted with a stand-in.
    role TEXT NOT NULL,
    overall_score INTEGER,
    ai_score INTEGER NOT NULL,
    resilience_score INTEGER,
    cost_score INTEGER,
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
