from atlas.parsing import normalize_asset_type, parse_money, parse_percent


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


def test_parse_percent_extracts_number_with_or_without_percent_sign() -> None:
    assert parse_percent("6.83%") == 6.83
    assert parse_percent("6.83") == 6.83


def test_parse_percent_handles_negative_values() -> None:
    assert parse_percent("-2.50%") == -2.5


def test_parse_percent_treats_placeholders_as_none() -> None:
    assert parse_percent("--") is None
    assert parse_percent("") is None
    assert parse_percent(None) is None


def test_parse_percent_returns_none_when_no_digits_present() -> None:
    assert parse_percent("N/A") is None
