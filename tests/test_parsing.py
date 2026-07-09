from atlas.db.database import normalize_asset_type, parse_money


def test_parse_money_strips_dollar_and_commas() -> None:
    assert parse_money("$9,846.00") == 9846.0
    assert parse_money("$4.96") == 4.96


def test_parse_money_treats_placeholders_as_zero() -> None:
    assert parse_money("--") == 0.0
    assert parse_money("N/A") == 0.0
    assert parse_money("") == 0.0
    assert parse_money(None) == 0.0


def test_normalize_asset_type_maps_schwab_labels() -> None:
    assert normalize_asset_type("Equity") == "equity"
    assert normalize_asset_type("ETFs & Closed End Funds") == "etf"
    assert normalize_asset_type("Mutual Fund") == "mutual_fund"
    assert normalize_asset_type("Cash and Money Market") == "cash"


def test_normalize_asset_type_handles_legacy_and_unknown() -> None:
    assert normalize_asset_type("ETF") == "etf"
    assert normalize_asset_type("Cash") == "cash"
    assert normalize_asset_type("--") == "other"
    assert normalize_asset_type(None) == "other"
