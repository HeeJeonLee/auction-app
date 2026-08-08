from analysis import passes_market_filters, needs_registry_verification


def test_passes_market_filters_kb_ok():
    row = {"부채총액": 800000000, "KB시세": 1200000000}
    assert passes_market_filters(row) is True


def test_passes_market_filters_kb_fail():
    row = {"부채총액": 1100000000, "KB시세": 1200000000}
    # debt 1.1B vs kb 1.2B -> threshold may be 0.85 or 0.8; ensure failing when >=85%
    assert passes_market_filters(row) is False


def test_needs_registry_on_rights():
    row = {"근저당여부": "예"}
    assert needs_registry_verification(row) is True


def test_needs_registry_on_value():
    row = {"낙찰예상가": 2500000000}
    assert needs_registry_verification(row) is True
