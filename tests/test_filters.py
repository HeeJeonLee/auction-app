from analysis import (
    passes_market_filters,
    needs_registry_verification,
    evaluate_case_policy,
    get_policy_reference,
    get_creditor_analysis_guidance,
    normalize_row,
    structure_rights_analysis,
)


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


def test_evaluate_case_policy_rejects_when_debt_exceeds_policy_limits():
    row = {"부채총액": 900000000, "KB시세": 1000000000, "낙찰예상가": 1000000000}
    decision = evaluate_case_policy(row)

    assert decision["decision"] == "reject"
    assert decision["keep_data"] is False


def test_evaluate_case_policy_keeps_when_within_policy_limits():
    row = {
        "부채총액": 800000000,
        "KB시세": 1000000000,
        "낙찰예상가": 1000000000,
        "권리요약": "근저당 없음; 압류 없음",
    }
    decision = evaluate_case_policy(row)

    assert decision["decision"] == "keep"
    assert decision["keep_data"] is True


def test_policy_reference_contains_creditor_analysis_rules():
    policy = get_policy_reference()

    assert policy["eligibility_rules"]["max_debt_to_kb_ratio"] == 0.85
    assert "creditor_analysis" in policy
    assert policy["creditor_analysis"]["patterns"]


def test_creditor_guidance_uses_policy_rules():
    guidance = get_creditor_analysis_guidance("수협")

    assert "수협" in guidance or "1금융" in guidance


def test_normalize_row_converts_numeric_strings():
    row = {"부채총액": "900000000", "KB시세": "1억원", "권리요약": "  "}
    normalized = normalize_row(row)

    assert normalized["부채총액"] == 900000000
    assert normalized["KB시세"] == 100000000


def test_structure_rights_analysis_produces_structured_output():
    row = {
        "근저당여부": "예",
        "압류여부": "아니오",
        "주요채권자": "수협",
    }
    structured = structure_rights_analysis(row)

    assert "근저당여부" in structured["rights_flags"]
    assert structured["risk_level"] in {"low", "medium", "high"}
    assert "수협" in structured["creditor_guidance"] or "1금융" in structured["creditor_guidance"]
